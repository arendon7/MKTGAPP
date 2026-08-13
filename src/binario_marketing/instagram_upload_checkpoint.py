from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .atomic import write_json_atomic
from .social_store import PROJECT_ID_RE, _now


_PUBLICATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_STAGES = {"UPLOADED", "FINISHED", "PUBLISHING", "PUBLISHED"}
_TRANSITIONS = {
    "UPLOADED": {"FINISHED"},
    "FINISHED": {"PUBLISHING"},
    "PUBLISHING": {"PUBLISHED"},
    "PUBLISHED": set(),
}


@dataclass(frozen=True)
class InstagramUploadCheckpoint:
    publication_id: str
    project_id: str
    target_id: str
    container_id: str
    stage: str
    remote_id: str | None
    created_at: str
    updated_at: str


class InstagramUploadCheckpointStore:
    """Secret-free resumable state for one managed Instagram Reel publication."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, publication_id: str) -> Path:
        value = str(publication_id or "").strip()
        if not _PUBLICATION_ID_RE.fullmatch(value):
            raise ValueError("invalid publication id")
        return self.root / f"{value}.json"

    @staticmethod
    def _validate_identity(project_id: str, target_id: str, container_id: str) -> tuple[str, str, str]:
        project = str(project_id or "").strip()
        target = str(target_id or "").strip()
        container = str(container_id or "").strip()
        if not PROJECT_ID_RE.fullmatch(project):
            raise ValueError("invalid project id")
        if not target or len(target) > 128:
            raise ValueError("invalid Instagram target id")
        if not container or len(container) > 256:
            raise ValueError("invalid Instagram container id")
        return project, target, container

    def get(self, publication_id: str) -> InstagramUploadCheckpoint | None:
        requested = str(publication_id or "").strip()
        path = self._path(requested)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid Instagram upload checkpoint")
        row = InstagramUploadCheckpoint(**payload)
        if row.publication_id != requested:
            raise ValueError("Instagram upload checkpoint publication id mismatch")
        if row.stage not in _STAGES:
            raise ValueError("invalid Instagram upload checkpoint stage")
        self._validate_identity(row.project_id, row.target_id, row.container_id)
        if row.remote_id is not None and (not str(row.remote_id).strip() or len(str(row.remote_id)) > 256):
            raise ValueError("invalid Instagram remote id")
        return row

    def uploaded(self, publication_id: str, project_id: str, target_id: str, container_id: str) -> InstagramUploadCheckpoint:
        project, target, container = self._validate_identity(project_id, target_id, container_id)
        existing = self.get(publication_id)
        if existing is not None:
            if (existing.project_id, existing.target_id, existing.container_id) != (project, target, container):
                raise ValueError("Instagram upload checkpoint identity mismatch")
            return existing
        now = _now()
        row = InstagramUploadCheckpoint(
            publication_id=str(publication_id),
            project_id=project,
            target_id=target,
            container_id=container,
            stage="UPLOADED",
            remote_id=None,
            created_at=now,
            updated_at=now,
        )
        write_json_atomic(self._path(publication_id), asdict(row))
        return row

    def _advance(self, publication_id: str, stage: str, *, remote_id: str | None = None) -> InstagramUploadCheckpoint:
        wanted = str(stage or "").strip().upper()
        if wanted not in _STAGES:
            raise ValueError("invalid Instagram upload checkpoint stage")
        current = self.get(publication_id)
        if current is None:
            raise ValueError("Instagram upload checkpoint is missing")
        if current.stage == wanted:
            return current
        if wanted not in _TRANSITIONS[current.stage]:
            raise ValueError(f"invalid Instagram upload checkpoint transition {current.stage} -> {wanted}")
        remote = current.remote_id
        if wanted == "PUBLISHED":
            remote = str(remote_id or "").strip()
            if not remote or len(remote) > 256:
                raise ValueError("Instagram remote id is required")
        elif remote_id is not None:
            raise ValueError("remote id is only valid for PUBLISHED checkpoint")
        row = replace(current, stage=wanted, remote_id=remote, updated_at=_now())
        write_json_atomic(self._path(publication_id), asdict(row))
        return row

    def finished(self, publication_id: str) -> InstagramUploadCheckpoint:
        return self._advance(publication_id, "FINISHED")

    def publishing(self, publication_id: str) -> InstagramUploadCheckpoint:
        return self._advance(publication_id, "PUBLISHING")

    def published(self, publication_id: str, remote_id: str) -> InstagramUploadCheckpoint:
        return self._advance(publication_id, "PUBLISHED", remote_id=remote_id)


__all__ = ["InstagramUploadCheckpoint", "InstagramUploadCheckpointStore"]
