#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.release-authorization.v1"
DECISION = "RELEASE_AUTHORIZED"
CONFIRMATION = "AUTHORIZE EXACT TESTED RELEASE"


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable(version: str) -> bool:
    value = str(version or "").strip().lower()
    return bool(value) and not any(token in value for token in (".dev", "-dev", "alpha", "beta", "rc"))


def authorize(
    attestation_path: Path,
    *,
    tag: str,
    authorized_by: str,
    note: str,
    confirmation: str,
) -> dict[str, Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_combined_uat_attestation import verify as verify_attestation

    attestation = verify_attestation(attestation_path)
    version = str(json.loads(attestation_path.read_text(encoding="utf-8")).get("binding", {}).get("product_version") or "")
    if not _stable(version):
        raise ValueError(f"release authorization requires a stable tested product version: {version}")
    expected_tag = f"v{version}"
    if tag != expected_tag:
        raise ValueError(f"release tag must exactly match tested version: {tag} != {expected_tag}")
    actor = str(authorized_by or "").strip()
    reason = str(note or "").strip()
    if len(actor) < 2:
        raise ValueError("authorized-by must identify the human release approver")
    if len(reason) < 12:
        raise ValueError("authorization note must contain a concrete release decision")
    if confirmation != CONFIRMATION:
        raise ValueError(f"explicit confirmation must equal: {CONFIRMATION}")

    core = {
        "schema": SCHEMA,
        "decision": DECISION,
        "git_sha": attestation["git_sha"],
        "product_version": version,
        "release_tag": tag,
        "candidate_source_sha256": attestation["candidate_source_sha256"],
        "combined_attestation_sha256": attestation["attestation_sha256"],
        "physical_uat_architecture": "arm64",
        "runtime_wave": attestation["runtime_wave"],
        "authorized_by": actor,
        "authorization_note": reason,
        "authorization_scope": "same_commit_exact_tag_source_equivalent_distribution_only",
        "release_authority": True,
        "production_ready": False,
    }
    return {
        **core,
        "authorized_at": datetime.now(timezone.utc).isoformat(),
        "authorization_sha256": _digest(core),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create explicit human release authorization only after combined physical UAT.")
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--authorized-by", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = authorize(
            args.attestation.expanduser().resolve(),
            tag=args.tag,
            authorized_by=args.authorized_by,
            note=args.note,
            confirmation=args.confirm,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(f"RELEASE AUTHORIZATION BLOCKED: {exc}") from exc
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "release_authorized": True,
        "git_sha": report["git_sha"],
        "release_tag": report["release_tag"],
        "authorization_sha256": report["authorization_sha256"],
        "production_ready": False,
        "output": str(output),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
