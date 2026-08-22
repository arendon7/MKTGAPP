#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.product-uat-evidence.v2"
CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
SESSION_SCHEMA = "binario.marketing.physical-uat-session.v1"
PHYSICAL_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _session_digest(session: dict[str, Any]) -> str:
    row = dict(session)
    row["evidence_sha256"] = None
    encoded = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _trusted_candidate(candidate: dict[str, Any]) -> bool:
    origin = candidate.get("build_origin") if isinstance(candidate.get("build_origin"), dict) else {}
    physical = candidate.get("physical_uat") if isinstance(candidate.get("physical_uat"), dict) else {}
    ref = str(origin.get("ref") or "")
    return bool(
        candidate.get("schema") == CANDIDATE_SCHEMA
        and candidate.get("role") == PHYSICAL_ROLE
        and candidate.get("architecture") == "arm64"
        and candidate.get("runtime_wave") == 76
        and candidate.get("certification_guard_wave") == 84
        and origin.get("event") == "push"
        and (ref == "refs/heads/main" or ref.startswith("refs/tags/v"))
        and origin.get("trusted_for_physical_uat") is True
        and physical.get("eligible_build_origin") is True
        and physical.get("automatic_pass") is False
    )


def collect(app: Path, session_path: Path) -> dict[str, Any]:
    app = app.expanduser().resolve()
    session_path = session_path.expanduser().resolve()
    resources = app / "Contents" / "Resources"
    candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    provenance_path = resources / "BUILD_PROVENANCE.json"
    candidate = _json(candidate_path)
    provenance = _json(provenance_path)
    session = _json(session_path)

    if not _trusted_candidate(candidate):
        raise ValueError("candidate is not trusted for physical UAT")
    if session.get("schema") != SESSION_SCHEMA:
        raise ValueError("unexpected physical product UAT session schema")
    if session.get("status") != "PASSED" or session.get("physical_uat_complete") is not True:
        raise ValueError("physical product UAT session is not complete PASS")
    machine = session.get("machine") if isinstance(session.get("machine"), dict) else {}
    if machine.get("physical_gate_eligible") is not True or machine.get("is_ci") is True:
        raise ValueError("physical product UAT session was not recorded on an eligible physical host")
    scenarios = list(session.get("scenarios") or [])
    required = [row for row in scenarios if row.get("required")]
    if not required or not all(row.get("status") == "PASS" for row in required):
        raise ValueError("all required physical product UAT scenarios must PASS")
    expected_digest = str(session.get("evidence_sha256") or "").lower()
    actual_digest = _session_digest(session)
    if len(expected_digest) != 64 or expected_digest != actual_digest:
        raise ValueError("physical product UAT evidence digest mismatch")

    git_sha = str(candidate.get("git_sha") or "")
    version = str(candidate.get("product_version") or "")
    build = session.get("build") if isinstance(session.get("build"), dict) else {}
    if len(git_sha) != 40 or provenance.get("git_sha") != git_sha or build.get("git_sha") != git_sha:
        raise ValueError("physical product UAT Git SHA does not match candidate")
    if provenance.get("architecture") != "arm64" or build.get("architecture") != "arm64":
        raise ValueError("physical product UAT architecture does not match arm64 candidate")
    if provenance.get("product_version") != version or build.get("product_version") != version:
        raise ValueError("physical product UAT version does not match candidate")

    candidate_source_sha256 = str(candidate.get("candidate_source_sha256") or "")
    if len(candidate_source_sha256) != 64:
        raise ValueError("candidate source SHA-256 missing or malformed")

    return {
        "schema": SCHEMA,
        "git_sha": git_sha,
        "architecture": "arm64",
        "product_version": version,
        "runtime_wave": 76,
        "certification_guard_wave": 85,
        "candidate_source_sha256": candidate_source_sha256,
        "candidate_manifest_sha256": _sha256(candidate_path),
        "company_id": session.get("company_id"),
        "session_id": session.get("id"),
        "session_evidence_sha256": expected_digest,
        "required_scenarios": len(required),
        "product_uat_passed": True,
        "release_authority": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export exact-candidate physical product UAT evidence for the dual UAT release gate.")
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--session", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = collect(args.app, args.session)
    except ValueError as exc:
        raise SystemExit(f"PRODUCT UAT COLLECTION BLOCKED: {exc}") from exc
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"product_uat_passed": True, "output": str(output), "git_sha": report["git_sha"]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
