from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic


PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
CHANNELS = {"facebook_page", "instagram"}
KINDS = {"text", "link", "image", "reel", "video"}
STATUSES = {"DRAFT", "QUEUED", "DELEGATED", "PUBLISHING", "PUBLISHED", "FAILED", "CANCELLED"}
_SECRET_KEYS = {
    "access_token",
    "token",
    "client_secret",
    "app_secret",
    "password",
    "authorization",
}
_ALLOWED_TRANSITIONS = {
    "DRAFT": {"QUEUED", "CANCELLED"},
    # DELEGATED is an authority boundary: once entered, the local scheduler cannot
    # start publication. Only explicit remote reconciliation may complete the row.
    "QUEUED": {"DELEGATED", "PUBLISHING", "CANCELLED"},
    "DELEGATED": {"PUBLISHED", "FAILED"},
    "PUBLISHING": {"PUBLISHED", "FAILED"},
    "FAILED": {"QUEUED", "CANCELLED"},
    "PUBLISHED": set(),
    "CANCELLED": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_when(value: str | None) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    row = datetime.fromisoformat(text)
    if row.tzinfo is None:
        raise ValueError("scheduled_for must include a timezone")
    return row.astimezone(timezone.utc)


def _assert_secret_free(value, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in _SECRET_KEYS:
                raise ValueError(f"credentials must not be persisted in {path}")
            _assert_secret_free(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_secret_free(child, f"{path}[{index}]")


@dataclass(frozen=True)
class Publication:
    id: str
    project_id: str
    channel: str
    target_id: str
    target_name: str
    kind: str
    message: str
    link_url: str | None
    media_url: str | None
    asset_id: str | None
    scheduled_for: str | None
    status: str
    remote_id: str | None
    error: str | None
    attempts: int
    created_at: str
    updated_at: str
    render_id: str | None = None


class SocialStore:
    """Durable publication queue. Provider credentials are never persisted."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, publication_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", publication_id):
            raise ValueError("invalid publication id")
        return self.root / f"{publication_id}.json"

    def _load(self, path: Path) -> Publication:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid publication payload")
        _assert_secret_free(payload)
        payload.setdefault("render_id", None)
        row = Publication(**payload)
        if row.status not in STATUSES:
            raise ValueError("invalid persisted publication status")
        return row

    def get(self, publication_id: str) -> Publication:
        with self._lock:
            path = self._path(publication_id)
            if not path.is_file():
                raise KeyError(publication_id)
            return self._load(path)

    def list(self, project_id: str | None = None) -> list[Publication]:
        if project_id is not None and not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("invalid project id")
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("*.json")]
        if project_id is not None:
            rows = [row for row in rows if row.project_id == project_id]
        return sorted(rows, key=lambda row: (row.scheduled_for or row.created_at, row.created_at, row.id))

    def create(self, project_id: str, payload: dict) -> Publication:
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("invalid project id")
        if not isinstance(payload, dict):
            raise ValueError("publication payload must be an object")
        _assert_secret_free(payload)
        channel = str(payload.get("channel") or "").strip().lower()
        target_id = str(payload.get("target_id") or "").strip()
        target_name = str(payload.get("target_name") or "").strip()[:160]
        kind = str(payload.get("kind") or "text").strip().lower()
        message = str(payload.get("message") or "").strip()
        link_url = str(payload.get("link_url") or "").strip() or None
        media_url = str(payload.get("media_url") or "").strip() or None
        asset_id = str(payload.get("asset_id") or "").strip() or None
        render_id = str(payload.get("render_id") or "").strip() or None
        if channel not in CHANNELS:
            raise ValueError("unsupported social channel")
        if not target_id or len(target_id) > 128:
            raise ValueError("target_id is required")
        if kind not in KINDS:
            raise ValueError("unsupported publication kind")
        if kind in {"text", "link"} and not message:
            raise ValueError("text and link publications require a message")
        if kind == "link" and not link_url:
            raise ValueError("link publications require link_url")
        if channel == "instagram" and kind in {"image", "reel", "video"} and not media_url:
            raise ValueError("Instagram media requires a public media_url reachable by Meta")
        if channel == "facebook_page" and kind == "reel" and not render_id:
            raise ValueError("Facebook Reel publication requires a completed local render_id")
        if len(message) > 20000:
            raise ValueError("publication message is too long")
        scheduled = _parse_when(payload.get("scheduled_for"))
        status = "QUEUED" if scheduled is not None else "DRAFT"
        now = _now()
        row = Publication(
            id=uuid.uuid4().hex,
            project_id=project_id,
            channel=channel,
            target_id=target_id,
            target_name=target_name,
            kind=kind,
            message=message,
            link_url=link_url,
            media_url=media_url,
            asset_id=asset_id,
            scheduled_for=scheduled.isoformat() if scheduled else None,
            status=status,
            remote_id=None,
            error=None,
            attempts=0,
            created_at=now,
            updated_at=now,
            render_id=render_id,
        )
        with self._lock:
            write_json_atomic(self._path(row.id), asdict(row))
        return row

    def transition(self, publication_id: str, status: str, *, remote_id: str | None = None, error: str | None = None, scheduled_for: str | None = None) -> Publication:
        status = str(status).strip().upper()
        if status not in STATUSES:
            raise ValueError("invalid publication status")
        with self._lock:
            current = self.get(publication_id)
            if status not in _ALLOWED_TRANSITIONS[current.status]:
                raise ValueError(f"invalid publication transition {current.status} -> {status}")
            scheduled = current.scheduled_for
            if status == "QUEUED":
                parsed = _parse_when(scheduled_for or current.scheduled_for or _now())
                scheduled = parsed.isoformat() if parsed else _now()
            attempts = current.attempts + (1 if status == "PUBLISHING" else 0)
            updated = replace(
                current,
                status=status,
                scheduled_for=scheduled,
                remote_id=(str(remote_id).strip() or None) if remote_id is not None else current.remote_id,
                error=(str(error).strip()[:2000] or None) if error is not None else (None if status in {"QUEUED", "DELEGATED", "PUBLISHED"} else current.error),
                attempts=attempts,
                updated_at=_now(),
            )
            write_json_atomic(self._path(updated.id), asdict(updated))
            return updated

    def queue(self, publication_id: str, scheduled_for: str | None = None) -> Publication:
        current = self.get(publication_id)
        if current.status not in {"DRAFT", "FAILED"}:
            raise ValueError("only draft or failed publications can be queued")
        return self.transition(publication_id, "QUEUED", scheduled_for=scheduled_for)

    def delegate(self, publication_id: str) -> Publication:
        """Withdraw local publication authority before a remote enqueue attempt."""
        current = self.get(publication_id)
        if current.status != "QUEUED":
            raise ValueError("only queued publications can be delegated")
        return self.transition(publication_id, "DELEGATED")

    def mark_delegated_published(self, publication_id: str, remote_id: str) -> Publication:
        current = self.get(publication_id)
        if current.status != "DELEGATED":
            raise ValueError("only delegated publications can be reconciled as published")
        clean_remote = str(remote_id or "").strip()
        if not clean_remote or len(clean_remote) > 256:
            raise ValueError("remote_id is required for delegated publication reconciliation")
        return self.transition(publication_id, "PUBLISHED", remote_id=clean_remote)

    def mark_delegated_failed(self, publication_id: str, error: str) -> Publication:
        current = self.get(publication_id)
        if current.status != "DELEGATED":
            raise ValueError("only delegated publications can be reconciled as failed")
        clean_error = str(error or "").strip()
        if not clean_error:
            raise ValueError("delegated failure requires an explicit reconciliation reason")
        return self.transition(publication_id, "FAILED", error=clean_error)

    def due(self, now: datetime | None = None, limit: int = 20) -> list[Publication]:
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if limit < 1 or limit > 500:
            raise ValueError("limit must be between 1 and 500")
        rows = []
        for row in self.list():
            if row.status != "QUEUED":
                continue
            when = _parse_when(row.scheduled_for)
            if when is not None and when <= moment:
                rows.append(row)
            if len(rows) >= limit:
                break
        return rows

    def recover_interrupted(self) -> list[Publication]:
        recovered = []
        for row in self.list():
            if row.status == "PUBLISHING":
                recovered.append(self.transition(row.id, "FAILED", error="publication interrupted by app restart; review remote state before retry"))
        return recovered
