#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify W90 release dry run evidence")
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()

    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    required = [
        "git_sha",
        "version",
        "source_digest",
        "uat_digest",
        "authorization_digest",
        "distribution_digest",
    ]

    missing = [key for key in required if not payload.get(key)]
    if missing:
        raise SystemExit(f"DRY RUN BLOCKED: missing evidence fields: {','.join(missing)}")

    if payload.get("publication_attempted") is True:
        raise SystemExit("DRY RUN BLOCKED: publication attempted")

    if payload.get("validation") != "PASS":
        raise SystemExit("DRY RUN BLOCKED: validation not PASS")

    print("RELEASE DRY RUN PASS")
    print("Publication intentionally disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
