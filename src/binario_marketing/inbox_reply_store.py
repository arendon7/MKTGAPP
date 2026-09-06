from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .atomic import write_json_atomic
from .social_store import _now


_STAGES = {"SENDING", "SENT", "AMBIGUOUS", "RECONCILED_SENT", "RETRY_ALLOWED"}
_BLOCKING_STAGES = {"SENDING", "AMBIGUOUS"}
_KINDS = {"facebook_message", "instagram_comment"}
_RECONCILIATION_OUTCOMES = {"SENT", "NOT_SENT"}


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

    def for_interaction(self, company_id: str, kind: str, interaction_id: str) -> list[InboxReplyCheckpoint]:
        company = str(company_id or "").strip()
        action = str(kind or "").strip()
        interaction = str(interaction_id or "").strip()
        if not company or not interaction:
            raise ValueError("company and interaction ids are required")
        if action not in _KINDS:
            raise ValueError("unsupported inbox reply kind")
        rows: list[InboxReplyCheckpoint] = []
        with self._lock:
            for path in self.root.glob("*.json"):
                row = self.get(path.stem)
                if row is not None and row.company_id == company and row.kind == action and row.interaction_id == interaction:
                    rows.append(row)
        rows.sort(key=lambda row: (row.updated_at, row.key))
        return rows

    def reconciliation_candidates(self, company_id: str, kind: str, interaction_id: str) -> list[dict]:
        """Expose only optimistic-concurrency metadata, never text hashes or checkpoint keys."""
        return [
            {"stage": row.stage, "updated_at": row.updated_at}
            for row in self.for_interaction(company_id, kind, interaction_id)
            if row.stage in _BLOCKING_STAGES
        ]

    def begin(self, company_id: str, kind: str, interaction_id: str, text: str) -> tuple[InboxReplyCheckpoint, bool]:
        key, text_sha = self.identity(company_id, kind, interaction_id, text)
        with self._lock:
            interaction_rows = self.for_interaction(company_id, kind, interaction_id)
            # A provider-effect ambiguity belongs to the interaction, not to one exact text.
            # Changing the text must never provide a blind-retry escape hatch.
            if any(row.stage in _BLOCKING_STAGES for row in interaction_rows):
                raise InboxReplyConflict(
                    "This interaction has an unfinished or ambiguous Meta attempt. Verify the provider and reconcile that attempt before sending any reply."
                )
            # A human-confirmed SENT resolution is deliberately terminal for this exact interaction.
            # A later genuine incoming message/comment must have a new provider interaction id.
            if any(row.stage == "RECONCILED_SENT" for row in interaction_rows):
                raise InboxReplyConflict(
                    "This interaction was manually confirmed as already sent after provider verification; a second reply is blocked."
                )
            existing = self.get(key)
            if existing is not None:
                if existing.stage == "SENT" and existing.remote_id:
                    return existing, True
                if existing.stage == "RETRY_ALLOWED":
                    row = replace(existing, stage="SENDING", remote_id=None, updated_at=_now())
                    write_json_atomic(self._path(key), asdict(row))
                    return row, False
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
            if current.stage in {"SENT", "RECONCILED_SENT"}:
                return current
            if current.stage == "RETRY_ALLOWED":
                raise InboxReplyConflict("reply checkpoint is already reconciled as not sent")
            row = replace(current, stage="AMBIGUOUS", updated_at=_now())
            write_json_atomic(self._path(key), asdict(row))
            return row

    def reconcile(
        self,
        company_id: str,
        kind: str,
        interaction_id: str,
        *,
        expected_stage: str,
        expected_updated_at: str,
        outcome: str,
    ) -> InboxReplyCheckpoint:
        """Record a human provider verification. This method performs no provider I/O."""
        expected = str(expected_stage or "").strip().upper()
        observed_at = str(expected_updated_at or "").strip()
        resolution = str(outcome or "").strip().upper()
        if expected not in _BLOCKING_STAGES:
            raise ValueError("expected_stage must be SENDING or AMBIGUOUS")
        if not observed_at:
            raise ValueError("expected_updated_at is required")
        if resolution not in _RECONCILIATION_OUTCOMES:
            raise ValueError("outcome must be SENT or NOT_SENT")
        with self._lock:
            blockers = [
                row for row in self.for_interaction(company_id, kind, interaction_id)
                if row.stage in _BLOCKING_STAGES
            ]
            if len(blockers) != 1:
                raise InboxReplyConflict("reply reconciliation requires exactly one blocking attempt; refresh the inbox and resolve any historical conflict manually")
            current = blockers[0]
            if current.stage != expected or current.updated_at != observed_at:
                raise InboxReplyConflict("reply reconciliation evidence is stale; refresh the inbox before resolving it")
            stage = "RECONCILED_SENT" if resolution == "SENT" else "RETRY_ALLOWED"
            row = replace(current, stage=stage, remote_id=current.remote_id if stage == "RECONCILED_SENT" else None, updated_at=_now())
            write_json_atomic(self._path(current.key), asdict(row))
            return row
