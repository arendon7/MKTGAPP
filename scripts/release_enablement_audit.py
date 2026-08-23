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
    bundle_verifier = (repo / "scripts/verify_release_evidence_bundle.py").read_text(encoding="utf-8")
    packaged_verifier = (repo / "scripts/verify_packaged_release_asset.py").read_text(encoding="utf-8")
    artifact_authorizer = (repo / "scripts/release_artifact_authorization.py").read_text(encoding="utf-8")
    provenance_authorizer = (repo / "scripts/release_ci_provenance_authorization.py").read_text(encoding="utf-8")
    publication_transaction = (repo / "scripts/publish_release_transaction.sh").read_text(encoding="utf-8")
    published_roundtrip = (repo / "scripts/verify_published_release_roundtrip.py").read_text(encoding="utf-8")

    # W93 remains the final mutation boundary. W94 only proves provenance and
    # emits a mutation-free handoff that W93 must validate before any provider
    # call. Source structure can prove ordering, never external runtime truth.
    publish_index = workflow.find("publish_release_transaction.sh")
    w91_authorize_index = workflow.find("release_evidence_chain.py authorize")
    w91_verify_index = workflow.find("release_evidence_chain.py verify-authorization")
    exact_bundle_index = workflow.find("verify_release_evidence_bundle.py")
    package_index = workflow.find("Package immutable release asset")
    roundtrip_index = workflow.find("Verify W92 packaged artifact round-trip trust")
    attest_index = workflow.find("Attest exact release ZIP with GitHub OIDC provenance")
    native_upload_index = workflow.find("uses: actions/upload-artifact@v4", attest_index)
    w92_authorize_index = workflow.find("release_artifact_authorization.py authorize")
    w92_verify_index = workflow.find("release_artifact_authorization.py verify-authorization")
    w94_authorize_index = workflow.find("release_ci_provenance_authorization.py authorize")
    w94_verify_index = workflow.find("release_ci_provenance_authorization.py verify-authorization")
    w91_cross_arch_before_publish = 0 <= w91_authorize_index < publish_index
    w91_verify_before_publish = 0 <= w91_verify_index < publish_index

    w94_handoff = publication_transaction.find("W94_STAGE_PROVENANCE_HANDOFF")
    w94_handoff_verify = publication_transaction.find("verify-transaction-handoff")
    preexisting_check = publication_transaction.find("W93_STAGE_PREEXISTING_RELEASE_CHECK")
    draft_create = publication_transaction.find("W93_STAGE_DRAFT_CREATE")
    authorized_upload = publication_transaction.find("W93_STAGE_AUTHORIZED_UPLOAD")
    first_download = publication_transaction.find("W93_STAGE_AUTHORIZED_DOWNLOAD")
    first_verify = publication_transaction.find("W93_STAGE_AUTHORIZED_VERIFY")
    evidence_upload = publication_transaction.find("W93_STAGE_EVIDENCE_UPLOAD")
    final_download = publication_transaction.find("W93_STAGE_FINAL_DOWNLOAD")
    final_verify = publication_transaction.find("W93_STAGE_FINAL_VERIFY")
    github_publish = publication_transaction.find("W93_STAGE_PUBLICATION")
    github_delete = publication_transaction.find("W93_STAGE_DRAFT_DELETE")

    structural = {
        "physical_uat_attestation_transport": "verify_combined_uat_attestation.py" in workflow and "PHYSICAL_UAT_ATTESTATION_B64" in workflow,
        "developer_id_credentials_gate": "APPLE_DEVELOPER_ID_P12_BASE64" in workflow and "BINARIO_CODESIGN_IDENTITY" in workflow,
        "notarization_gate": "notarize_release_candidate.sh" in workflow and "verify_distribution_trust.py" in workflow,
        "distribution_rebuild_identity": "DISTRIBUTION_REBUILD.json" in gate and "binario.marketing.distribution-rebuild.v1" in distribution_writer,
        "production_gate_before_packaging": workflow.find("release_candidate_gate.py") != -1 and package_index != -1 and workflow.find("release_candidate_gate.py") < package_index,
        "release_tag_verifier": "verify_release_tag.py" in workflow and "verify_pipeline_contract" in tag_verifier,
        "runtime_wave_76_preserved": all("RUNTIME_WAVE = 76" in source for source in (evidence_chain, packaged_verifier, artifact_authorizer, provenance_authorizer)),
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
        "post_package_roundtrip_before_native_artifact_upload": roundtrip_index != -1 and native_upload_index > roundtrip_index,
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
        "w94_provenance_action_pinned": "uses: actions/attest@v4.2.1" in workflow,
        "w94_provenance_uses_exact_packaged_path": "id: package" in workflow and 'echo "zip_path=$ZIP" >> "$GITHUB_OUTPUT"' in workflow and "subject-path: ${{ steps.package.outputs.zip_path }}" in workflow,
        "w94_sigstore_bundle_persisted": "steps.attest.outputs.bundle-path" in workflow and "CI-PROVENANCE-${{ matrix.arch }}.sigstore.json" in workflow,
        "w94_attestation_after_roundtrip_before_native_upload": 0 <= roundtrip_index < attest_index < native_upload_index,
        "w94_build_job_has_oidc_attestation_permissions": all(marker in workflow for marker in ("id-token: write", "attestations: write", "artifact-metadata: write")),
        "w94_global_permissions_are_read_only": "permissions:\n  contents: read\n\njobs:" in workflow,
        "w94_publish_job_contents_write_is_scoped": "publish-release:\n    needs: build-native\n    permissions:\n      contents: write" in workflow,
        "w94_ci_provenance_authorization_schema": "binario.marketing.release-ci-provenance-authorization.v2" in provenance_authorizer,
        "w94_uses_github_oidc_and_slsa": "https://token.actions.githubusercontent.com" in provenance_authorizer and "https://slsa.dev/provenance/v1" in provenance_authorizer,
        "w94_denies_self_hosted_attestations": "--deny-self-hosted-runners" in provenance_authorizer,
        "w94_binds_repo_workflow_ref_and_digest": all(marker in provenance_authorizer for marker in ("--repo", "--signer-workflow", "--source-ref", "--source-digest")),
        "w94_transaction_script_hash_bound": "transaction_script_sha256" in provenance_authorizer and "script_sha256" in provenance_authorizer,
        "w94_handoff_is_non_publication_authority": '"transaction_handoff_authority": True' in provenance_authorizer and '"publication_authority": False' in provenance_authorizer,
        "w94_authorization_after_w92_before_w93": 0 <= w92_verify_index < w94_authorize_index < w94_verify_index < publish_index,
        "w94_authorization_manifest_required": "RELEASE-CI-PROVENANCE-AUTHORIZATION.json" in workflow and "RELEASE-CI-PROVENANCE-AUTHORIZATION.json" in publication_transaction,
        "w94_transaction_handoff_precedes_any_w93_mutation": 0 <= w94_handoff <= w94_handoff_verify < preexisting_check < draft_create,
        "w94_transaction_handoff_verifies_exact_publisher": "--transaction-script scripts/publish_release_transaction.sh" in publication_transaction and "verify-transaction-handoff" in publication_transaction,
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
        "exact_published_evidence_bytes_verified_at_tag_runtime": False,
        "cross_arch_release_authorization_verified_at_tag_runtime": False,
        "w91_cross_arch_release_authorization_verified_at_tag_runtime": False,
        "post_package_roundtrip_trust_verified_for_arm64_at_tag_runtime": False,
        "post_package_roundtrip_trust_verified_for_x86_64_at_tag_runtime": False,
        "w92_artifact_publication_authorization_verified_at_tag_runtime": False,
        "w93_github_release_draft_roundtrip_verified_at_tag_runtime": False,
        "w93_github_release_final_inventory_verified_at_tag_runtime": False,
        "w93_github_release_published_after_roundtrip_at_tag_runtime": False,
        "github_oidc_provenance_verified_for_arm64_at_tag_runtime": False,
        "github_oidc_provenance_verified_for_x86_64_at_tag_runtime": False,
        "w94_ci_provenance_handoff_verified_at_tag_runtime": False,
    }
    return {
        "schema": "binario.marketing.release-enablement-audit.v6",
        "version": version,
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
        "notes": "Source readiness never authorizes publication. Physical UAT evidence and Apple credentials remain external runtime facts. W91 cross-architecture evidence remains mandatory; W92 requires exact native ZIP round-trip trust; W94 requires GitHub OIDC/Sigstore provenance for both exact ZIPs and a hash-bound, mutation-free handoff into the publisher. W93 remains the final fail-closed GitHub Release draft transaction and still performs exact byte verification of the authorized and final draft inventories before publication. None of these external runtime facts are inferred from source.",
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
