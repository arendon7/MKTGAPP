from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE, Company
from .projects import ProjectStore
from .social_store import _now


@dataclass(frozen=True)
class CompanyWorkspace:
    company_id: str
    project_id: str
    created_at: str
    updated_at: str


class CompanyWorkspaceStore:
    """Binds one durable creative/paid-media project to one marketing company.

    The project remains a normal canonical ProjectStore project, so video, renders,
    transcription and paid-media storage keep using already-certified paths.
    """

    def __init__(self, root: Path, projects: ProjectStore):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.projects = projects
        self._lock = threading.RLock()

    def _path(self, company_id: str) -> Path:
        value = str(company_id or "").strip()
        if not COMPANY_ID_RE.fullmatch(value):
            raise ValueError("invalid company id")
        return self.root / f"{value}.json"

    def _load(self, path: Path) -> CompanyWorkspace:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid company workspace payload")
        row = CompanyWorkspace(**payload)
        if not COMPANY_ID_RE.fullmatch(row.company_id):
            raise ValueError("invalid company workspace company id")
        # Fail closed if the mapped project disappeared or was manually damaged.
        self.projects.path_for(row.project_id)
        return row

    def get(self, company_id: str) -> CompanyWorkspace | None:
        with self._lock:
            path = self._path(company_id)
            if not path.is_file():
                return None
            return self._load(path)

    def ensure(self, company: Company) -> CompanyWorkspace:
        with self._lock:
            existing = self.get(company.id)
            if existing is not None:
                return existing
            project = self.projects.create(f"{company.name} · Marketing Studio")
            now = _now()
            row = CompanyWorkspace(company_id=company.id, project_id=project.id, created_at=now, updated_at=now)
            write_json_atomic(self._path(company.id), asdict(row))
            return row


__all__ = ["CompanyWorkspace", "CompanyWorkspaceStore"]
