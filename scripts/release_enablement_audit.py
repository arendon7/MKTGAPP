#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


def _load_version(repo: Path) -> tuple[str, bool, str | None]:
    sys.path.insert(0, str(repo / "src"))
    try:
        from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__
        return __version__, RELEASE_READY, RELEASE_TAG
    finally:
        try:
            sys.path.remove(str(repo / "src"))
        except ValueError:
            pass


def audit(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    version, release_ready, release_tag = _load_version(repo)
    workflow = (repo / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
    gate = (repo / "scripts/release_candidate_gate.py").read_text(encoding="utf-8")
    tag_verifier = (repo / "scripts/verify_release_tag.py").read_text(encoding="utf-8")
    distribution_writer = (repo / "scripts/write_distribution_rebuild_manifest.py").read_text(encoding="utf-8")
    evidence_chain = (repo / "scripts/release_evidence_chain.py").read_text(encoding="utf-8")

    publish_index = workflow.find("Publish permanent GitHub Release")
    authorize_index = workflow.find("release_evidence_chain.py authorize")
    verify_authorization_index = workflow.find("release_evidence_chain.py verify-authorization")
    structural = {
        "physical_uat_attestation_transport": "verify_combined_uat_attestation.py" in workflow and "PHYSICAL_UAT_ATTESTATION_B64" in workflow,
        "developer_id_credentials_gate": "APPLE_DEVELOPER_ID_P12_BASE64" in workflow and "BINARIO_CODESIGN_IDENTITY" in workflow,
        "notarization_gate": "notarize_release_candidate.sh" in workflow and "verify_distribution_trust.py" in workflow,
        "distribution_rebuild_identity": "DISTRIBUTION_REBUILD.json" in gate and "binario.marketing.distribution-rebuild.v1" in distribution_writer,
        "production_gate_before_packaging": workflow.find("release_candidate_gate.py") != -1 and workflow.find("Package immutable release asset") != -1 and workflow.find("release_candidate_gate.py") < workflow.find("Package immutable release asset"),
        "release_tag_verifier": "verify_release_tag.py" in workflow and "verify_pipeline_contract" in tag_verifier,
        "runtime_wave_76_preserved": "RUNTIME_WAVE = 76" in evidence_chain,
        "release_evidence_chain": "binario.marketing.release-evidence-chain.v1" in evidence_chain and "release_evidence_chain.py write-asset" in workflow,
        "production_gate_evidence_persisted": "production-gate-${{ matrix.arch }}.json" in workflow and "| tee" in workflow,
        "cross_arch_release_authorization_before_publish": 0 <= authorize_index < publish_index,
        "final_authorization_verification_before_publish": 0 <= verify_authorization_index < publish_index,
        "release_authorization_manifest_uploaded": "RELEASE-AUTHORIZATION.json" in workflow and "binario.marketing.release-authorization.v1" in evidence_chain,
        "per_arch_release_manifests_are_non_authoritative": 'release_authority": False' in evidence_chain and 'publication_authority": False' in evidence_chain,
        "exact_evidence_digest_binding": "exact_evidence_digest_binding_verified" in evidence_chain and "distribution_rebuild_manifest_sha256" in gate,
    }

    blockers: list[str] = []
    if ".dev" in version.lower() or re.search(r"(?:rc|alpha|beta)", version, re.I):
        blockers.append("development_version")
    if release_ready is not True:
        blockers.append("release_flag_false")
    if not release_tag:
        blockers.append("release_tag_missing")
    if release_tag and release_tag != f"v{version}":
        blockers.append("release_tag_version_mismatch")
    for name, ok in structural.items():
        if not ok:
            blockers.append(f"structural_gate_missing:{name}")

    source_ready = not blockers
    external_requirements = {
        "physical_uat_attestation_verified_at_tag_runtime": False,
        "apple_distribution_credentials_verified_at_tag_runtime": False,
        "developer_id_signature_verified_at_tag_runtime": False,
        "apple_notarization_verified_at_tag_runtime": False,
        "distribution_rebuild_verified_at_tag_runtime": False,
        "production_gate_passed_at_tag_runtime": False,
        "exact_evidence_digests_verified_at_tag_runtime": False,
        "cross_arch_release_authorization_verified_at_tag_runtime": False,
    }
    return {
        "schema": "binario.marketing.release-enablement-audit.v3",
        "version": version,
        "release_ready": release_ready,
        "release_tag": release_tag,
        "runtime_wave": 76,
        "certification_guard_wave": 91,
        "structural_gates": structural,
        "source_status": "SOURCE_CONTRACT_READY" if source_ready else "BLOCKED",
        "status": "BLOCKED" if not source_ready else "AWAITING_OPERATIONAL_AUTHORIZATION",
        "blocker_codes": blockers,
        "external_runtime_requirements": external_requirements,
        "operational_authorization": False,
        "mutations_performed": False,
        "release_authority": False,
        "production_ready": False,
        "notes": "Source readiness never authorizes release. Physical UAT evidence, Apple credentials, Developer ID signing, notarization, source-equivalent distribution rebuild verification, exact evidence-file digest binding, the per-architecture production gates and the final cross-architecture authorization must all pass in the tag-triggered runtime before publication.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed source audit before BINARIO Marketing release enablement.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--expect-blocked", action="store_true")
    args = parser.parse_args()
    report = audit(args.repo)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.expect_blocked:
        return 0 if report["status"] == "BLOCKED" else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
