from __future__ import annotations

import json
import os
from pathlib import Path

from .atomic import write_json_atomic
from .config import default_paths
from .wave27_instagram_local import Wave27SocialStore
from .wave28_background import Wave28SocialScheduler


def run_once(data_root: Path | None = None) -> dict:
    root = (data_root or default_paths().home).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    social = Wave27SocialStore(root / "State" / "social")
    scheduler = Wave28SocialScheduler(social)
    rows = scheduler.run_once(limit=20)
    status = scheduler.status()
    payload = {
        "schema": "binario.marketing.background-social.v1",
        "pid": os.getpid(),
        "data_root": str(root),
        "processed": len(rows),
        "last_run_at": status.get("last_run_at"),
        "last_error": status.get("last_error"),
        "recovered": status.get("recovered_on_start", 0),
        "lock_skips": status.get("lock_skips", 0),
    }
    state_root = root / "State" / "background_social"
    state_root.mkdir(parents=True, exist_ok=True)
    write_json_atomic(state_root / "status.json", payload)
    return payload


def main() -> int:
    payload = run_once()
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return 0 if not payload.get("last_error") else 1


if __name__ == "__main__":
    raise SystemExit(main())
