from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from .atomic import write_json_atomic


@dataclass(frozen=True)
class Asset:
    id: str
    name: str
    kind: str
    relative_path: str
    imported_at: str
    sha256: str | None = None
    bytes: int | None = None


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    directory: str
    created_at: str


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-.")
    return cleaned or "project"


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


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

    def asset(self, project_id: str, asset_id: str) -> Asset:
        match = next((item for item in self.assets(project_id) if item.id == asset_id), None)
        if match is None:
            raise KeyError(asset_id)
        return match

    @staticmethod
    def _managed_child(root: Path, relative_path: str) -> Path:
        root = root.resolve()
        candidate = (root / relative_path).resolve()
        if root != candidate and root not in candidate.parents:
            raise ValueError("managed path escaped project root")
        return candidate

    def asset_path(self, project_id: str, asset_id: str) -> Path:
        project_root = self.path_for(project_id)
        asset = self.asset(project_id, asset_id)
        path = self._managed_child(project_root, asset.relative_path)
        assets_root = (project_root / "assets").resolve()
        if assets_root not in path.parents:
            raise ValueError("asset path escaped managed assets root")
        if not path.is_file():
            raise FileNotFoundError(path)
        return path

    def exports_dir(self, project_id: str) -> Path:
        path = self.path_for(project_id) / "exports"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def export_path(self, project_id: str, filename: str) -> Path:
        safe = Path(filename).name
        if not safe or safe in {".", ".."}:
            raise ValueError("invalid export filename")
        root = self.exports_dir(project_id).resolve()
        path = (root / safe).resolve()
        if root not in path.parents:
            raise ValueError("export path escaped managed exports root")
        return path

    def _target(self, project_id: str, filename: str) -> tuple[str, Path, str]:
        folder = self.path_for(project_id)
        original_name = Path(filename).name.strip() or "upload.bin"
        source_name = Path(original_name)
        asset_id = uuid.uuid4().hex[:12]
        safe_name = _slug(source_name.stem) + source_name.suffix.lower()
        target_name = f"{asset_id}-{safe_name}"
        return asset_id, folder / "assets" / target_name, original_name

    def _register(self, project_id: str, asset: Asset) -> Asset:
        folder = self.path_for(project_id)
        items = [asdict(item) for item in self.assets(project_id)]
        items.append(asdict(asset))
        write_json_atomic(folder / "assets.json", items)
        return asset

    def add_asset(self, project_id: str, source: Path, kind: str) -> Asset:
        if not source.is_file():
            raise FileNotFoundError(source)
        asset_id, target, original_name = self._target(project_id, source.name)
        shutil.copy2(source, target)
        digest, size = _sha256_file(target)
        asset = Asset(asset_id, original_name, kind, f"assets/{target.name}", datetime.now(timezone.utc).isoformat(), digest, size)
        return self._register(project_id, asset)

    def add_uploaded_asset(self, project_id: str, filename: str, kind: str, stream: BinaryIO, length: int) -> Asset:
        if length < 0:
            raise ValueError("invalid upload length")
        asset_id, target, original_name = self._target(project_id, filename)
        temporary = target.with_name(f".{target.name}.part")
        digest = hashlib.sha256()
        remaining = length
        written = 0
        try:
            with temporary.open("xb") as output:
                while remaining:
                    chunk = stream.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("upload body ended before Content-Length")
                    output.write(chunk)
                    digest.update(chunk)
                    written += len(chunk)
                    remaining -= len(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        asset = Asset(asset_id, original_name, kind, f"assets/{target.name}", datetime.now(timezone.utc).isoformat(), digest.hexdigest(), written)
        return self._register(project_id, asset)

    def remove_asset(self, project_id: str, asset_id: str) -> bool:
        folder = self.path_for(project_id)
        current = self.assets(project_id)
        match = next((item for item in current if item.id == asset_id), None)
        if match is None:
            return False
        managed = self.asset_path(project_id, asset_id)
        if managed.exists():
            managed.unlink()
        write_json_atomic(folder / "assets.json", [asdict(item) for item in current if item.id != asset_id])
        return True
