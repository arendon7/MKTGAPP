#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    manifest = []
    for relative in sorted(files):
        path = ROOT / relative
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest.append({"path": relative, "sha256": digest, "bytes": path.stat().st_size})
    payload = {"files": manifest}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    payload["tree_sha256"] = hashlib.sha256(canonical).hexdigest()
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
