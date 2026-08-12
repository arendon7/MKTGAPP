#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_SUFFIXES = {".zip", ".dmg", ".app"}
REQUIRED = {
    "pyproject.toml",
    "docs/recovery/RECOVERY_STATE.json",
    "apps/editor-video/manifest.json",
    "src/binario_marketing/projects.py",
    "src/binario_marketing/video/clipper.py",
}


def tracked_files() -> list[str]:
    proc = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True)
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def main() -> int:
    tracked = tracked_files()
    missing = sorted(REQUIRED - set(tracked))
    forbidden = [path for path in tracked if Path(path).suffix.lower() in FORBIDDEN_SUFFIXES]
    if missing or forbidden:
        if missing:
            print("missing required source:", *missing, sep="\n- ")
        if forbidden:
            print("generated artifacts must not be canonical source:", *forbidden, sep="\n- ")
        return 1
    print(f"PASS: canonical source tree ({len(tracked)} tracked files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
