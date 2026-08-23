#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from release_evidence_chain import verify_asset_evidence


def _sha256(path: Path) -> str:
    if not path.is_file():
        raise ValueError(f"release evidence file missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid release evidence JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"release evidence JSON must be an object: {path}")
    return data


def verify_bundle(
    *,
    evidence_path: Path,
    asset_dir: Path,
    release_manifest: Path,
    uat_evidence: Path,
    distribution_evidence: Path,
    production_gate_evidence: Path,
    expected_tag: str | None = None,
    expected_git_sha: str | None = None,
) -> dict[str, Any]:
    evidence_path = evidence_path.expanduser().resolve()
    uat_evidence = uat_evidence.expanduser().resolve()
    distribution_evidence = distribution_evidence.expanduser().resolve()
    production_gate_evidence = production_gate_evidence.expanduser().resolve()

    evidence = verify_asset_evidence(
        evidence_path,
        asset_dir=asset_dir,
        release_manifest=release_manifest,
        expected_tag=expected_tag,
        expected_git_sha=expected_git_sha,
    )
    uat = evidence.get("physical_uat") or {}
    trust = evidence.get("distribution_trust") or {}
    gate = evidence.get("production_gate") or {}

    actual_uat_sha = _sha256(uat_evidence)
    actual_distribution_sha = _sha256(distribution_evidence)
    actual_gate_sha = _sha256(production_gate_evidence)
    if actual_uat_sha != uat.get("evidence_file_sha256"):
        raise ValueError("published physical UAT evidence bytes do not match the authorized native chain")
    if actual_distribution_sha != trust.get("evidence_file_sha256"):
        raise ValueError("published distribution trust bytes do not match the authorized native chain")
    if actual_gate_sha != gate.get("evidence_file_sha256"):
        raise ValueError("published production gate bytes do not match the authorized native chain")

    gate_json = _load(production_gate_evidence)
    exact_gate_bindings = {
        "uat_evidence_file_sha256": actual_uat_sha,
        "uat_attestation_sha256": uat.get("attestation_sha256"),
        "distribution_evidence_file_sha256": actual_distribution_sha,
        "distribution_trust_evidence_sha256": trust.get("evidence_sha256"),
        "distribution_rebuild_manifest_sha256": (evidence.get("distribution_rebuild") or {}).get("manifest_sha256"),
    }
    for key, expected in exact_gate_bindings.items():
        if gate_json.get(key) != expected:
            raise ValueError(f"published production gate exact binding mismatch: {key}")

    return {
        "schema": "binario.marketing.release-evidence-bundle-verification.v1",
        "architecture": evidence.get("architecture"),
        "git_sha": evidence.get("git_sha"),
        "tag": evidence.get("tag"),
        "release_evidence_sha256": evidence.get("evidence_sha256"),
        "asset_sha256": (evidence.get("asset") or {}).get("sha256"),
        "physical_uat_file_sha256": actual_uat_sha,
        "distribution_trust_file_sha256": actual_distribution_sha,
        "production_gate_file_sha256": actual_gate_sha,
        "exact_published_evidence_verified": True,
        "release_authority": False,
        "publication_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that the exact W91 evidence files being published match one authorized native chain.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--release-manifest", type=Path, required=True)
    parser.add_argument("--uat-evidence", type=Path, required=True)
    parser.add_argument("--distribution-evidence", type=Path, required=True)
    parser.add_argument("--production-gate-evidence", type=Path, required=True)
    parser.add_argument("--expected-tag")
    parser.add_argument("--expected-git-sha")
    args = parser.parse_args()
    try:
        report = verify_bundle(
            evidence_path=args.evidence,
            asset_dir=args.asset_dir,
            release_manifest=args.release_manifest,
            uat_evidence=args.uat_evidence,
            distribution_evidence=args.distribution_evidence,
            production_gate_evidence=args.production_gate_evidence,
            expected_tag=args.expected_tag,
            expected_git_sha=args.expected_git_sha,
        )
    except ValueError as exc:
        raise SystemExit(f"W91 RELEASE EVIDENCE BUNDLE BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
