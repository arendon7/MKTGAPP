#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".zip", ".dmg", ".app"}
REQUIRED = {
    "pyproject.toml",
    "docs/recovery/RECOVERY_STATE.json",
    "docs/recovery/APP_REGISTRY.json",
    "apps/editor-video/manifest.json",
    "src/binario_marketing/projects.py",
    "src/binario_marketing/video/clipper.py",
    "src/binario_marketing/video/session.py",
    "src/binario_marketing/editor_store.py",
    "src/binario_marketing/service.py",
    "web/index.html",
    "web/app.js",
    "web/styles.css",
    "scripts/full_mac_python_runtime.env",
    "scripts/bootstrap_full_mac_python.sh",
    "scripts/build_full_mac_app.sh",
    "scripts/audit_full_mac_app.sh",
    ".github/workflows/full-mac-app.yml",
}


def tracked_files() -> list[str]:
    proc = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    tracked = tracked_files()
    missing = sorted(REQUIRED - set(tracked))
    forbidden = [path for path in tracked if Path(path).suffix.lower() in FORBIDDEN_SUFFIXES]
    manifests = sorted(ROOT.glob("apps/*/manifest.json"))
    manifest_ids = [json.loads(path.read_text(encoding="utf-8"))["id"] for path in manifests]
    errors = []
    if len(manifests) != 12:
        errors.append(f"expected 12 app manifests, found {len(manifests)}")
    if len(manifest_ids) != len(set(manifest_ids)):
        errors.append("duplicate app manifest ids")
    if missing or forbidden or errors:
        for item in errors: print("ERROR:", item)
        if missing: print("missing required source:", *missing, sep="\n- ")
        if forbidden: print("generated artifacts must not be canonical source:", *forbidden, sep="\n- ")
        return 1
    print(f"PASS: canonical source tree ({len(tracked)} tracked files, 12/12 apps, local web + FULL MAC builders present)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
