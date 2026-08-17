from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .atomic import write_json_atomic
from .social_store import _now


_STAGES = {"SENDING", "SENT", "AMBIGUOUS"}
_KINDS = {"facebook_message", "instagram_comment"}


class InboxReplyConflict(RuntimeError):
    """Raised when a prior provider attempt makes a blind retry unsafe."""


@dataclass(frozen=True)
class InboxReplyCheckpoint:
    key: str
    company_id: str
    kind: str
    interaction_id: str
    text_sha256: str
    stage: str
    remote_id: str | None
    created_at: str
    updated_at: str


class InboxReplyStore:
    """Secret-free idempotency checkpoints for explicit inbox replies."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def normalize_text(value: object) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("reply text is required")
        if len(text) > 2000:
            raise ValueError("reply text is too long")
        return text

    @staticmethod
    def identity(company_id: str, kind: str, interaction_id: str, text: str) -> tuple[str, str]:
        company = str(company_id or "").strip()
        action = str(kind or "").strip()
        interaction = str(interaction_id or "").strip()
        if not company or not interaction:
            raise ValueError("company and interaction ids are required")
        if action not in _KINDS:
            raise ValueError("unsupported inbox reply kind")
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        raw = f"{company}\0{action}\0{interaction}\0{text_sha}".encode("utf-8")
        key = hashlib.sha256(raw).hexdigest()
        return key, text_sha

    def _path(self, key: str) -> Path:
        value = str(key or "").strip().lower()
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("invalid inbox reply checkpoint key")
        return self.root / f"{value}.json"

    def get(self, key: str) -> InboxReplyCheckpoint | None:
        with self._lock:
            path = self._path(key)
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("invalid inbox reply checkpoint")
            row = InboxReplyCheckpoint(**payload)
            if row.stage not in _STAGES or row.kind not in _KINDS or row.key != key:
                raise ValueError("invalid inbox reply checkpoint")
            return row

    def begin(self, company_id: str, kind: str, interaction_id: str, text: str) -> tuple[InboxReplyCheckpoint, bool]:
        key, text_sha = self.identity(company_id, kind, interaction_id, text)
        with self._lock:
            existing = self.get(key)
            if existing is not None:
                if existing.stage == "SENT" and existing.remote_id:
                    return existing, True
                raise InboxReplyConflict(
                    "This reply already has an unfinished or ambiguous Meta attempt. Refresh the inbox and verify the provider before trying again."
                )
            now = _now()
            row = InboxReplyCheckpoint(
                key=key,
                company_id=str(company_id).strip(),
                kind=kind,
                interaction_id=str(interaction_id).strip(),
                text_sha256=text_sha,
                stage="SENDING",
                remote_id=None,
                created_at=now,
                updated_at=now,
            )
            write_json_atomic(self._path(key), asdict(row))
            return row, False

    def sent(self, key: str, remote_id: str) -> InboxReplyCheckpoint:
        remote = str(remote_id or "").strip()
        if not remote:
            raise ValueError("provider reply id is required")
        with self._lock:
            current = self.get(key)
            if current is None or current.stage != "SENDING":
                raise InboxReplyConflict("reply checkpoint is not in SENDING state")
            row = replace(current, stage="SENT", remote_id=remote, updated_at=_now())
            write_json_atomic(self._path(key), asdict(row))
            return row

    def ambiguous(self, key: str) -> InboxReplyCheckpoint:
        with self._lock:
            current = self.get(key)
            if current is None:
                raise InboxReplyConflict("reply checkpoint is missing")
            if current.stage == "SENT":
                return current
            row = replace(current, stage="AMBIGUOUS", updated_at=_now())
            write_json_atomic(self._path(key), asdict(row))
            return row
