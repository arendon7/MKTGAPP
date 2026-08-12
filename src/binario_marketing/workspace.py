from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .registries import Registries


@dataclass(frozen=True)
class WorkspaceProject:
    id: str
    name: str
    active_app: str | None
    status: str
    updated_at: str


@dataclass(frozen=True)
class Handoff:
    id: str
    project_id: str
    from_app: str
    to_app: str
    summary: str
    artifact_refs: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    created_at: str


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.projects_path = root / "projects.json"
        self.handoffs_path = root / "handoffs.json"
        self.registries = Registries.at(root / "registries")

    def _load(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def projects(self) -> list[WorkspaceProject]:
        return [WorkspaceProject(**row) for row in self._load(self.projects_path)]

    def handoffs(self) -> list[Handoff]:
        rows = []
        for row in self._load(self.handoffs_path):
            row["artifact_refs"] = tuple(row.get("artifact_refs", []))
            row["evidence_refs"] = tuple(row.get("evidence_refs", []))
            rows.append(Handoff(**row))
        return rows

    def upsert_project(self, project_id: str, name: str, active_app: str | None = None, status: str = "active") -> WorkspaceProject:
        project = WorkspaceProject(project_id, name, active_app, status, datetime.now(timezone.utc).isoformat())
        rows = {item.id: item for item in self.projects()}
        rows[project_id] = project
        write_json_atomic(self.projects_path, [asdict(rows[key]) for key in sorted(rows)])
        self.registries.timeline.append("workspace.project.updated", {"project_id": project_id, "active_app": active_app, "status": status})
        return project

    def handoff(self, project_id: str, from_app: str, to_app: str, summary: str, artifact_refs: tuple[str, ...] = (), evidence_refs: tuple[str, ...] = ()) -> Handoff:
        if not any(item.id == project_id for item in self.projects()):
            raise KeyError(project_id)
        handoff = Handoff(
            uuid.uuid4().hex[:12], project_id, from_app, to_app, summary,
            tuple(artifact_refs), tuple(evidence_refs), datetime.now(timezone.utc).isoformat(),
        )
        rows = [asdict(item) for item in self.handoffs()]
        rows.append(asdict(handoff))
        write_json_atomic(self.handoffs_path, rows)
        self.registries.timeline.append("workspace.handoff", {"handoff_id": handoff.id, "project_id": project_id, "from_app": from_app, "to_app": to_app})
        return handoff
