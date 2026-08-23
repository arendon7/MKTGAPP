#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.release-uat-evidence.v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"


def _load(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema") != SCHEMA:
        raise SystemExit("invalid release UAT evidence")
    return data


def _validate_source_contract(data: dict[str, Any]) -> None:
    state = data.get("source_release_state")
    tag = data.get("source_release_tag")
    version = str(data.get("version") or "")
    if state == LOCKED_SOURCE:
        if tag is not None:
            raise SystemExit("LOCKED_SOURCE UAT evidence cannot carry a prepared release tag")
        return
    if state == PREPARED_RELEASE:
        if tag != f"v{version}" or ".dev" in version.lower() or "rc" in version.lower():
            raise SystemExit("PREPARED_RELEASE UAT evidence has incoherent version/tag binding")
        return
    raise SystemExit("UAT evidence source release state is missing or invalid")


def _recompute(data: dict[str, Any]) -> None:
    manual = data.get("manual_steps") or []
    automatic = bool(data.get("automatic_passed"))
    statuses = [row.get("status") for row in manual if isinstance(row, dict)]
    if not automatic:
        data["uat_passed"] = False
        data["overall"] = "AUTOMATIC_FAIL"
    elif any(status == "FAIL" for status in statuses):
        data["uat_passed"] = False
        data["overall"] = "UAT_FAIL"
    elif statuses and all(status == "PASS" for status in statuses):
        data["uat_passed"] = True
        data["overall"] = "UAT_PASS"
    else:
        data["uat_passed"] = False
        data["overall"] = "AUTOMATIC_PASS_MANUAL_PENDING"
    data["updated_at"] = datetime.now(timezone.utc).isoformat()


def main() -> int:
    ap = argparse.ArgumentParser(description="Record one explicit physical UAT result for an exact release candidate.")
    ap.add_argument("--evidence", type=Path, required=True)
    ap.add_argument("--step", required=True)
    ap.add_argument("--status", choices=("PASS", "FAIL"), required=True)
    ap.add_argument("--note", required=True, help="Concrete evidence/observation for this manual gate.")
    args = ap.parse_args()

    path = args.evidence.expanduser().resolve()
    data = _load(path)
    if not data.get("git_sha") or data.get("architecture") != "arm64":
        raise SystemExit("UAT evidence is not bound to an arm64 git_sha candidate")
    source_digest = str(data.get("candidate_source_sha256") or "")
    manifest_digest = str(data.get("candidate_manifest_sha256") or "")
    if not SHA256_RE.fullmatch(source_digest) or not SHA256_RE.fullmatch(manifest_digest):
        raise SystemExit("UAT evidence is not bound to the exact physical candidate digests")
    if data.get("runtime_wave") != 76:
        raise SystemExit("UAT evidence runtime is not the canonical Wave 76 product runtime")
    _validate_source_contract(data)
    if data.get("release_authority") not in {None, False} or data.get("publication_authority") not in {None, False} or data.get("production_ready") not in {None, False}:
        raise SystemExit("physical UAT evidence must not carry release/publication authority")
    if not data.get("automatic_passed"):
        raise SystemExit("automatic checks must pass before recording manual UAT")
    note = args.note.strip()
    if not note:
        raise SystemExit("manual UAT note must contain concrete evidence/observation")

    target = None
    for row in data.get("manual_steps") or []:
        if isinstance(row, dict) and row.get("id") == args.step:
            target = row
            break
    if target is None:
        raise SystemExit(f"unknown UAT step: {args.step}")

    target["status"] = args.status
    target["note"] = note
    target["recorded_at"] = datetime.now(timezone.utc).isoformat()
    _recompute(data)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"step": args.step, "status": args.status, "overall": data["overall"], "uat_passed": data["uat_passed"], "git_sha": data["git_sha"], "candidate_source_sha256": source_digest, "source_release_state": data.get("source_release_state"), "source_release_tag": data.get("source_release_tag"), "architecture": data["architecture"]}, ensure_ascii=False, indent=2))
    return 2 if data["overall"] in {"AUTOMATIC_FAIL", "UAT_FAIL"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
