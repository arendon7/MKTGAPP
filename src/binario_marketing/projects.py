from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    kind: str
    relative_path: str
    imported_at: str


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    directory: str
    created_at: str


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    return cleaned or "project"


class ProjectStore:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.registry_path = self.root / "projects.json"

    def _registry(self) -> list[dict]:
        if not self.registry_path.exists():
            return []
        return json.loads(self.registry_path.read_text(encoding="utf-8"))

    def list_projects(self) -> list[Project]:
        return [Project(**item) for item in self._registry()]

    def create(self, name: str) -> Project:
        project_id = uuid.uuid4().hex[:12]
        directory = f"{_slug(name)}-{project_id}"
        created_at = datetime.now(timezone.utc).isoformat()
        project = Project(project_id, name.strip() or "Untitled", directory, created_at)
        folder = self.root / directory
        (folder / "assets").mkdir(parents=True, exist_ok=False)
        (folder / "exports").mkdir()
        write_json_atomic(folder / "project.json", asdict(project))
        write_json_atomic(folder / "assets.json", [])
        registry = self._registry()
        registry.append(asdict(project))
        write_json_atomic(self.registry_path, registry)
        return project

    def path_for(self, project_id: str) -> Path:
        for project in self.list_projects():
            if project.id == project_id:
                return self.root / project.directory
        raise KeyError(project_id)

    def assets(self, project_id: str) -> list[Asset]:
        path = self.path_for(project_id) / "assets.json"
        return [Asset(**item) for item in json.loads(path.read_text(encoding="utf-8"))]

    def add_asset(self, project_id: str, source: Path, kind: str) -> Asset:
        if not source.is_file():
            raise FileNotFoundError(source)
        folder = self.path_for(project_id)
        asset_id = uuid.uuid4().hex[:12]
        safe_name = _slug(source.stem) + source.suffix.lower()
        target_name = f"{asset_id}-{safe_name}"
        target = folder / "assets" / target_name
        shutil.copy2(source, target)
        asset = Asset(asset_id, source.name, kind, f"assets/{target_name}", datetime.now(timezone.utc).isoformat())
        items = [asdict(a) for a in self.assets(project_id)]
        items.append(asdict(asset))
        write_json_atomic(folder / "assets.json", items)
        return asset

    def remove_asset(self, project_id: str, asset_id: str) -> bool:
        folder = self.path_for(project_id)
        current = self.assets(project_id)
        match = next((a for a in current if a.id == asset_id), None)
        if match is None:
            return False
        managed = (folder / match.relative_path).resolve()
        assets_root = (folder / "assets").resolve()
        if assets_root not in managed.parents:
            raise ValueError("asset path escaped managed root")
        if managed.exists():
            managed.unlink()
        write_json_atomic(folder / "assets.json", [asdict(a) for a in current if a.id != asset_id])
        return True
