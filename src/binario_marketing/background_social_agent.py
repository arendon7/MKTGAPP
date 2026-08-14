from __future__ import annotations

import json
import os
from pathlib import Path

from .atomic import write_json_atomic
from .background_scheduler import LockedSocialScheduler
from .config import default_paths
from .meta_graph import MetaGraphClient
from .wave27_instagram_local import Wave27SocialStore


STATUS_SCHEMA = "binario.marketing.background-social.v2"


def run_once(data_root: Path | None = None) -> dict:
    """Process due publications once; touch only social queue and status sidecar."""
    root = (data_root or default_paths().home).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    social = Wave27SocialStore(root / "State" / "social")
    scheduler = LockedSocialScheduler(social)
    rows = scheduler.run_once(limit=20)
    status = scheduler.status()
    connection = MetaGraphClient.diagnose_env()
    payload = {
        "schema": STATUS_SCHEMA,
        "pid": os.getpid(),
        "processed": len(rows),
        "last_run_at": status.get("last_run_at"),
        "last_error": status.get("last_error"),
        "recovered": status.get("recovered_on_start", 0),
        "lock_skips": status.get("lock_skips", 0),
        "credential_configured": connection.configured,
        "credential_source": connection.credential_source,
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
