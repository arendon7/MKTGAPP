#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.release-authorization.v1"
DECISION = "RELEASE_AUTHORIZED"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_SCOPE = "same_commit_exact_tag_source_equivalent_distribution_only"


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid release authorization: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("release authorization must be a JSON object")
    return data


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _stable(version: str) -> bool:
    value = str(version or "").strip().lower()
    return bool(value) and not any(token in value for token in (".dev", "-dev", "alpha", "beta", "rc"))


def verify(
    authorization_path: Path,
    *,
    attestation_path: Path,
    expected_git_sha: str | None = None,
    expected_tag: str | None = None,
    expected_version: str | None = None,
    expected_source_sha256: str | None = None,
) -> dict[str, Any]:
    authorization_path = authorization_path.expanduser().resolve()
    attestation_path = attestation_path.expanduser().resolve()
    data = _load(authorization_path)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify_combined_uat_attestation import verify as verify_attestation

    attestation = verify_attestation(attestation_path, expected_git_sha=expected_git_sha)
    if data.get("schema") != SCHEMA:
        raise ValueError("unexpected release authorization schema")
    if data.get("decision") != DECISION or data.get("release_authority") is not True:
        raise ValueError("release authorization decision is not active")
    if data.get("production_ready") is not False:
        raise ValueError("release authorization must not itself claim production readiness")
    if data.get("authorization_scope") != EXPECTED_SCOPE:
        raise ValueError("release authorization scope drift")
    if data.get("runtime_wave") != EXPECTED_RUNTIME_WAVE:
        raise ValueError("release authorization runtime wave drift")
    git_sha = str(data.get("git_sha") or "")
    version = str(data.get("product_version") or "")
    tag = str(data.get("release_tag") or "")
    source_sha = str(data.get("candidate_source_sha256") or "")
    if len(git_sha) != 40:
        raise ValueError("release authorization git SHA is malformed")
    if not _stable(version):
        raise ValueError("release authorization product version is not stable")
    if tag != f"v{version}":
        raise ValueError("release authorization tag does not match product version")
    if len(source_sha) != 64:
        raise ValueError("release authorization source digest is malformed")
    if data.get("physical_uat_architecture") != "arm64":
        raise ValueError("release authorization must derive from arm64 physical UAT")
    if data.get("combined_attestation_sha256") != attestation.get("attestation_sha256"):
        raise ValueError("release authorization is not bound to this combined physical UAT attestation")
    if git_sha != attestation.get("git_sha"):
        raise ValueError("release authorization git SHA differs from physical UAT")
    if source_sha != attestation.get("candidate_source_sha256"):
        raise ValueError("release authorization source digest differs from physical UAT")
    raw_attestation = _load(attestation_path)
    attested_version = str((raw_attestation.get("binding") or {}).get("product_version") or "")
    if version != attested_version:
        raise ValueError("release authorization version differs from physically tested version")
    if expected_git_sha is not None and git_sha != expected_git_sha:
        raise ValueError(f"release authorization git SHA mismatch: {git_sha} != {expected_git_sha}")
    if expected_tag is not None and tag != expected_tag:
        raise ValueError(f"release authorization tag mismatch: {tag} != {expected_tag}")
    if expected_version is not None and version != expected_version:
        raise ValueError(f"release authorization version mismatch: {version} != {expected_version}")
    if expected_source_sha256 is not None and source_sha != expected_source_sha256:
        raise ValueError("release authorization source digest mismatch")
    actor = str(data.get("authorized_by") or "").strip()
    note = str(data.get("authorization_note") or "").strip()
    if len(actor) < 2 or len(note) < 12:
        raise ValueError("release authorization lacks concrete human decision metadata")
    expected_digest = str(data.get("authorization_sha256") or "")
    core = dict(data)
    core.pop("authorized_at", None)
    core.pop("authorization_sha256", None)
    if len(expected_digest) != 64 or _digest(core) != expected_digest:
        raise ValueError("release authorization digest mismatch")
    return {
        "schema": SCHEMA,
        "decision": DECISION,
        "git_sha": git_sha,
        "product_version": version,
        "release_tag": tag,
        "candidate_source_sha256": source_sha,
        "combined_attestation_sha256": attestation["attestation_sha256"],
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "authorized_by": actor,
        "authorization_scope": EXPECTED_SCOPE,
        "authorization_sha256": expected_digest,
        "release_authority": True,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify explicit human release authorization against exact combined physical UAT.")
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--expected-git-sha")
    parser.add_argument("--expected-tag")
    parser.add_argument("--expected-version")
    parser.add_argument("--expected-source-sha256")
    args = parser.parse_args()
    try:
        report = verify(
            args.authorization,
            attestation_path=args.attestation,
            expected_git_sha=args.expected_git_sha,
            expected_tag=args.expected_tag,
            expected_version=args.expected_version,
            expected_source_sha256=args.expected_source_sha256,
        )
    except ValueError as exc:
        raise SystemExit(f"RELEASE AUTHORIZATION BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
