#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"
INVALID_SOURCE_CONTRACT = "INVALID_SOURCE_CONTRACT"


def _load_version(repo: Path) -> tuple[str, bool, str | None, str]:
    sys.path.insert(0, str(repo / "src"))
    try:
        from binario_marketing.release_readiness import source_release_state
        from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__
        try:
            state = source_release_state(version=__version__, release_ready=RELEASE_READY, release_tag=RELEASE_TAG)
        except ValueError:
            state = INVALID_SOURCE_CONTRACT
        return __version__, RELEASE_READY, RELEASE_TAG, state
    finally:
        try:
            sys.path.remove(str(repo / "src"))
        except ValueError:
            pass


def _normalize_loaded_version(values: tuple[Any, ...]) -> tuple[str, bool, str | None, str]:
    """Preserve the historical W89/W90 audit seam while adding W94 source state.

    Older regression tests intentionally mock ``_load_version`` with the original
    three-value contract. W94 accepts that seam and deterministically derives the
    fourth value instead of forcing historical source-authorization tests to change.
    """
    if len(values) == 4:
        version, release_ready, release_tag, state = values
        return str(version), bool(release_ready), release_tag, str(state)
    if len(values) != 3:
        raise ValueError(f"unexpected release version tuple shape: {len(values)}")
    version, release_ready, release_tag = values
    version = str(version)
    release_ready = bool(release_ready)
    release_tag = str(release_tag) if release_tag is not None else None
    is_development = bool(
        not version.strip()
        or ".dev" in version.lower()
        or "-dev" in version.lower()
        or re.search(r"(?:rc|alpha|beta)", version, re.I)
    )
    if release_ready is False and release_tag is None:
        state = LOCKED_SOURCE
    elif release_ready is True and not is_development and release_tag == f"v{version}":
        state = PREPARED_RELEASE
    else:
        state = INVALID_SOURCE_CONTRACT
    return version, release_ready, release_tag, state


def audit(repo: Path) -> dict[str, Any]:
    repo = repo.resolve()
    version, release_ready, release_tag, source_release_state = _normalize_loaded_version(tuple(_load_version(repo)))
    workflow = (repo / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
    gate = (repo / "scripts/release_candidate_gate.py").read_text(encoding="utf-8")
    tag_verifier = (repo / "scripts/verify_release_tag.py").read_text(encoding="utf-8")
    distribution_writer = (repo / "scripts/write_distribution_rebuild_manifest.py").read_text(encoding="utf-8")
    evidence_chain = (repo / "scripts/release_evidence_chain.py").read_text(encoding="utf-8")
    bundle_verifier = (repo / "scripts/verify_release_evidence_bundle.py").read_text(encoding="utf-8")
    packaged_verifier = (repo / "scripts/verify_packaged_release_asset.py").read_text(encoding="utf-8")
    artifact_authorizer = (repo / "scripts/release_artifact_authorization.py").read_text(encoding="utf-8")
    publication_transaction = (repo / "scripts/publish_release_transaction.sh").read_text(encoding="utf-8")
    published_roundtrip = (repo / "scripts/verify_published_release_roundtrip.py").read_text(encoding="utf-8")
    candidate_writer = (repo / "scripts/write_physical_uat_candidate.py").read_text(encoding="utf-8")
    readiness = (repo / "src/binario_marketing/release_readiness.py").read_text(encoding="utf-8")

    publish_index = workflow.find("publish_release_transaction.sh")
    w91_authorize_index = workflow.find("release_evidence_chain.py authorize")
    w91_verify_index = workflow.find("release_evidence_chain.py verify-authorization")
    exact_bundle_index = workflow.find("verify_release_evidence_bundle.py")
    package_index = workflow.find("Package immutable release asset")
    roundtrip_index = workflow.find("Verify W92 packaged artifact round-trip trust")
    w92_authorize_index = workflow.find("release_artifact_authorization.py authorize")
    w92_verify_index = workflow.find("release_artifact_authorization.py verify-authorization")
    w91_cross_arch_before_publish = 0 <= w91_authorize_index < publish_index
    w91_verify_before_publish = 0 <= w91_verify_index < publish_index

    draft_create = publication_transaction.find("W93_STAGE_DRAFT_CREATE")
    authorized_upload = publication_transaction.find("W93_STAGE_AUTHORIZED_UPLOAD")
    first_download = publication_transaction.find("W93_STAGE_AUTHORIZED_DOWNLOAD")
    first_verify = publication_transaction.find("W93_STAGE_AUTHORIZED_VERIFY")
    evidence_upload = publication_transaction.find("W93_STAGE_EVIDENCE_UPLOAD")
    final_download = publication_transaction.find("W93_STAGE_FINAL_DOWNLOAD")
    final_verify = publication_transaction.find("W93_STAGE_FINAL_VERIFY")
    github_publish = publication_transaction.find("W93_STAGE_PUBLICATION")
    github_delete = publication_transaction.find("W93_STAGE_DRAFT_DELETE")
    preexisting_check = publication_transaction.find("W93_STAGE_PREEXISTING_RELEASE_CHECK")

    structural = {
        "physical_uat_attestation_transport": "verify_combined_uat_attestation.py" in workflow and "PHYSICAL_UAT_ATTESTATION_B64" in workflow,
        "developer_id_credentials_gate": "APPLE_DEVELOPER_ID_P12_BASE64" in workflow and "BINARIO_CODESIGN_IDENTITY" in workflow,
        "notarization_gate": "notarize_release_candidate.sh" in workflow and "verify_distribution_trust.py" in workflow,
        "distribution_rebuild_identity": "DISTRIBUTION_REBUILD.json" in gate and "binario.marketing.distribution-rebuild.v1" in distribution_writer,
        "production_gate_before_packaging": workflow.find("release_candidate_gate.py") != -1 and package_index != -1 and workflow.find("release_candidate_gate.py") < package_index,
        "release_tag_verifier": "verify_release_tag.py" in workflow and "verify_pipeline_contract" in tag_verifier,
        "runtime_wave_76_preserved": "RUNTIME_WAVE = 76" in evidence_chain and "RUNTIME_WAVE = 76" in packaged_verifier and "RUNTIME_WAVE = 76" in artifact_authorizer,
        "release_evidence_chain": "binario.marketing.release-evidence-chain.v1" in evidence_chain and "release_evidence_chain.py write-asset" in workflow,
        "production_gate_evidence_persisted": "production-gate-${{ matrix.arch }}.json" in workflow and "| tee" in workflow,
        "exact_published_evidence_bytes_verified": "release-evidence-bundle-verification.v1" in bundle_verifier and 0 <= exact_bundle_index < w91_authorize_index,
        "cross_arch_release_authorization_before_publish": w91_cross_arch_before_publish,
        "final_authorization_verification_before_publish": w91_verify_before_publish,
        "w91_cross_arch_release_authorization_before_publish": w91_cross_arch_before_publish,
        "w91_final_authorization_verification_before_publish": w91_verify_before_publish,
        "w91_release_authorization_manifest_present": "RELEASE-AUTHORIZATION.json" in workflow and "binario.marketing.release-authorization.v1" in evidence_chain,
        "per_arch_release_manifests_are_non_authoritative": 'release_authority": False' in evidence_chain and 'publication_authority": False' in evidence_chain,
        "exact_evidence_digest_binding": "exact_evidence_digest_binding_verified" in evidence_chain and "distribution_rebuild_manifest_sha256" in gate,
        "post_package_roundtrip_schema": "binario.marketing.post-package-trust.v1" in packaged_verifier,
        "post_package_roundtrip_after_packaging": 0 <= package_index < roundtrip_index,
        "post_package_roundtrip_before_native_artifact_upload": roundtrip_index != -1 and workflow.find("uses: actions/upload-artifact@v4", roundtrip_index) > roundtrip_index,
        "post_package_roundtrip_apple_trust_checks": all(marker in packaged_verifier for marker in ("codesign", "stapler", "spctl", "Developer ID Application:")),
        "post_package_roundtrip_is_non_authoritative": 'release_authority": False' in packaged_verifier and 'publication_authority": False' in packaged_verifier,
        "w92_artifact_authorization_schema": "binario.marketing.release-artifact-authorization.v1" in artifact_authorizer,
        "w92_authorization_after_w91": 0 <= w91_verify_index < w92_authorize_index,
        "w92_authorization_after_roundtrip_verification": 0 <= roundtrip_index < w92_authorize_index,
        "w92_final_authorization_verification_before_publish": 0 <= w92_verify_index < publish_index,
        "w92_artifact_authorization_manifest_required_for_publish": "RELEASE-ARTIFACT-AUTHORIZATION.json" in workflow and 0 <= w92_verify_index < publish_index,
        "w93_transaction_delegated_after_w92_authorization": 0 <= w92_verify_index < publish_index,
        "w93_github_roundtrip_schema": "binario.marketing.github-release-roundtrip.v1" in published_roundtrip,
        "w93_draft_before_github_roundtrip": 0 <= preexisting_check < draft_create < authorized_upload < first_download < first_verify,
        "w93_final_inventory_roundtrip_before_publication": 0 <= first_verify < evidence_upload < final_download < final_verify < github_publish,
        "w93_github_roundtrip_before_publication": 0 <= final_verify < github_publish,
        "w93_draft_cleanup_fail_closed": all(marker in publication_transaction for marker in ("CREATE_ATTEMPTED=1", "TRANSACTION_COMPLETE=1", "isDraft")) and 0 <= github_delete,
        "w93_preexisting_release_is_never_owned": 0 <= preexisting_check < draft_create and 'release already exists for $GITHUB_REF_NAME' in publication_transaction,
        "w93_publication_is_transactional": all(marker in publication_transaction for marker in ("--draft", "--draft=false", "GITHUB-RELEASE-ROUNDTRIP.json", "GITHUB-RELEASE-FINAL-VERIFY.json", "github-release-expected")),
        "w94_two_state_source_contract": all(marker in readiness for marker in ("LOCKED_SOURCE", "PREPARED_RELEASE", "source_release_state")),
        "w94_exact_physical_candidate_is_main_only": 'ref == "refs/heads/main"' in candidate_writer and 'ref.startswith("refs/tags/v")' not in candidate_writer,
        "w94_production_requires_prepared_uat": "prepared_release_uat_required" in gate and "prepared_release_tag_mismatch" in gate,
        "w94_tag_preflight_binds_prepared_uat": "--expected-source-release-state PREPARED_RELEASE" in workflow and '--expected-release-tag "$GITHUB_REF_NAME"' in workflow,
        "w94_intel_smoke_uses_canonical_version": "from binario_marketing.version import __version__" in workflow and "row['product_version']==__version__" in workflow,
    }

    blockers: list[str] = []
    if source_release_state == INVALID_SOURCE_CONTRACT:
        blockers.append("source_release_contract_invalid")
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

    source_ready = source_release_state == PREPARED_RELEASE and not blockers
    external_requirements = {
        "physical_uat_attestation_verified_at_tag_runtime": False,
        "apple_distribution_credentials_verified_at_tag_runtime": False,
        "developer_id_signature_verified_at_tag_runtime": False,
        "apple_notarization_verified_at_tag_runtime": False,
        "distribution_rebuild_verified_at_tag_runtime": False,
        "production_gate_passed_at_tag_runtime": False,
        "exact_evidence_digests_verified_at_tag_runtime": False,
        "exact_published_evidence_bytes_verified_at_tag_runtime": False,
        "cross_arch_release_authorization_verified_at_tag_runtime": False,
        "w91_cross_arch_release_authorization_verified_at_tag_runtime": False,
        "post_package_roundtrip_trust_verified_for_arm64_at_tag_runtime": False,
        "post_package_roundtrip_trust_verified_for_x86_64_at_tag_runtime": False,
        "w92_artifact_publication_authorization_verified_at_tag_runtime": False,
        "w93_github_release_draft_roundtrip_verified_at_tag_runtime": False,
        "w93_github_release_final_inventory_verified_at_tag_runtime": False,
        "w93_github_release_published_after_roundtrip_at_tag_runtime": False,
        "w94_prepared_release_physical_uat_verified_at_tag_runtime": False,
    }
    return {
        "schema": "binario.marketing.release-enablement-audit.v6",
        "version": version,
        "source_release_state": source_release_state,
        "release_ready": release_ready,
        "release_tag": release_tag,
        "runtime_wave": 76,
        "certification_guard_wave": 94,
        "structural_gates": structural,
        "source_status": "SOURCE_CONTRACT_READY" if source_ready else "BLOCKED",
        "status": "BLOCKED" if not source_ready else "AWAITING_OPERATIONAL_AUTHORIZATION",
        "blocker_codes": blockers,
        "external_runtime_requirements": external_requirements,
        "operational_authorization": False,
        "mutations_performed": False,
        "release_authority": False,
        "publication_authority": False,
        "production_ready": False,
        "notes": "Source readiness never authorizes publication. W94 adds a SHA-stable PREPARED_RELEASE source state that must exist before physical UAT and remain bound to the same git SHA/source/version/tag. Physical UAT evidence and Apple credentials remain external runtime facts. W91 cross-architecture evidence remains mandatory; W92 requires exact native ZIP round-trip trust; W93 requires a fail-closed GitHub Release draft transaction with exact byte verification before publication. None of these external runtime facts are inferred from source.",
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
