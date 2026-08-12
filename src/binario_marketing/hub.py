from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppManifest:
    app_id: str
    name: str
    service: str
    entrypoint: str
    capabilities: tuple[str, ...]
    path: Path


def discover_apps(root: Path) -> list[AppManifest]:
    apps_root = root / "apps"
    found: list[AppManifest] = []
    if not apps_root.exists():
        return found
    for manifest_path in sorted(apps_root.glob("*/manifest.json")):
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = {"id", "name", "service", "entrypoint"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"{manifest_path}: missing {sorted(missing)}")
        found.append(
            AppManifest(
                app_id=str(data["id"]),
                name=str(data["name"]),
                service=str(data["service"]),
                entrypoint=str(data["entrypoint"]),
                capabilities=tuple(data.get("capabilities", [])),
                path=manifest_path,
            )
        )
    ids = [app.app_id for app in found]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate app id")
    return found
