from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic


@dataclass(frozen=True)
class FactoryProject:
    id: str
    name: str
    stage: str
    updated_at: str


class AppFactoryRegistry:
    STAGES = ("product_lab", "engineering_delivery", "operation")

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry = root / "projects.json"

    def list(self) -> list[FactoryProject]:
        if not self.registry.exists():
            return []
        return [FactoryProject(**row) for row in json.loads(self.registry.read_text(encoding="utf-8"))]

    def upsert(self, project_id: str, name: str, stage: str) -> FactoryProject:
        if stage not in self.STAGES:
            raise ValueError(stage)
        project = FactoryProject(project_id, name, stage, datetime.now(timezone.utc).isoformat())
        rows = {item.id: item for item in self.list()}
        rows[project_id] = project
        write_json_atomic(self.registry, [asdict(rows[key]) for key in sorted(rows)])
        return project
