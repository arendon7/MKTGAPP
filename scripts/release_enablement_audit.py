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

    publish_index = workflow.find("Publish permanent GitHub Release")
    w91_authorize_index = workflow.find("release_evidence_chain.py authorize")
    w91_verify_index = workflow.find("release_evidence_chain.py verify-authorization")
    exact_bundle_index = workflow.find("verify_release_evidence_bundle.py")
    package_index = workflow.find("Package immutable release asset")
    roundtrip_index = workflow.find("Verify W92 packaged artifact round-trip trust")
    attest_index = workflow.find("Attest exact release ZIP with GitHub OIDC provenance")
    native_upload_index = workflow.find("uses: actions/upload-artifact@v4", roundtrip_index)
    w92_authorize_index = workflow.find("release_artifact_authorization.py authorize")
    w92_verify_index = workflow.find("release_artifact_authorization.py verify-authorization")
    w93_authorize_index = workflow.find("release_ci_provenance_authorization.py authorize")
    w93_verify_index = workflow.find("release_ci_provenance_authorization.py verify-authorization")
    w91_cross_arch_before_publish = 0 <= w91_authorize_index < publish_index
    w91_verify_before_publish = 0 <= w91_verify_index < publish_index

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
        "per_arch_release_manifests_are_non_authoritative": 'release_authority\": False' in evidence_chain and 'publication_authority\": False' in evidence_chain,
        "exact_evidence_digest_binding": "exact_evidence_digest_binding_verified" in evidence_chain and "distribution_rebuild_manifest_sha256" in gate,
        "post_package_roundtrip_schema": "binario.marketing.post-package-trust.v1" in packaged_verifier,
        "post_package_roundtrip_after_packaging": 0 <= package_index < roundtrip_index,
        "post_package_roundtrip_before_native_artifact_upload": roundtrip_index != -1 and native_upload_index > roundtrip_index,
        "post_package_roundtrip_apple_trust_checks": all(marker in packaged_verifier for marker in ("codesign", "stapler", "spctl", "Developer ID Application:")),
        "post_package_roundtrip_is_non_authoritative": 'release_authority\": False' in packaged_verifier and 'publication_authority\": False' in packaged_verifier,
        "w92_artifact_authorization_schema": "binario.marketing.release-artifact-authorization.v1" in artifact_authorizer,
        "w92_authorization_after_w91": 0 <= w91_verify_index < w92_authorize_index,
        "w92_authorization_after_roundtrip_verification": 0 <= roundtrip_index < w92_authorize_index,
        "w92_final_authorization_verification_before_publish": 0 <= w92_verify_index < publish_index,
        "w92_artifact_authorization_manifest_required_for_publish": "RELEASE-ARTIFACT-AUTHORIZATION.json" in workflow and 0 <= w92_verify_index < publish_index,
        "w93_provenance_action_pinned": "uses: actions/attest@v4.2.1" in workflow,
        "w93_provenance_uses_exact_packaged_path": "id: package" in workflow and 'echo "zip_path=$ZIP" >> "$GITHUB_OUTPUT"' in workflow and "subject-path: ${{ steps.package.outputs.zip_path }}" in workflow,
        "w93_sigstore_bundle_persisted": "steps.attest.outputs.bundle-path" in workflow and "CI-PROVENANCE-${{ matrix.arch }}.sigstore.json" in workflow,
        "w93_attestation_after_roundtrip_before_upload": 0 <= roundtrip_index < attest_index < native_upload_index,
        "w93_build_job_has_oidc_attestation_permissions": all(marker in workflow for marker in ("id-token: write", "attestations: write", "artifact-metadata: write")),
        "w93_global_permissions_are_read_only": "permissions:\n  contents: read\n\njobs:" in workflow,
        "w93_publish_job_contents_write_is_scoped": "publish-release:\n    needs: build-native\n    permissions:\n      contents: write" in workflow,
        "w93_ci_provenance_authorization_schema": "binario.marketing.release-ci-provenance-authorization.v1" in provenance_authorizer,
        "w93_uses_github_oidc_and_slsa": "https://token.actions.githubusercontent.com" in provenance_authorizer and "https://slsa.dev/provenance/v1" in provenance_authorizer,
        "w93_denies_self_hosted_attestations": "--deny-self-hosted-runners" in provenance_authorizer,
        "w93_binds_repo_workflow_ref_and_digest": all(marker in provenance_authorizer for marker in ("--repo", "--signer-workflow", "--source-ref", "--source-digest")),
        "w93_authorization_after_w92": 0 <= w92_verify_index < w93_authorize_index,
        "w93_final_authorization_verification_before_publish": 0 <= w93_verify_index < publish_index,
        "w93_final_manifest_required_for_publish": "RELEASE-CI-PROVENANCE-AUTHORIZATION.json" in workflow and 0 <= w93_verify_index < publish_index,
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
        "github_oidc_provenance_verified_for_arm64_at_tag_runtime": False,
        "github_oidc_provenance_verified_for_x86_64_at_tag_runtime": False,
        "w93_ci_provenance_publication_authorization_verified_at_tag_runtime": False,
    }
    return {
        "schema": "binario.marketing.release-enablement-audit.v5",
        "version": version,
        "release_ready": release_ready,
        "release_tag": release_tag,
        "runtime_wave": 76,
        "certification_guard_wave": 93,
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
        "notes": "Source readiness never authorizes publication. Physical UAT evidence and Apple credentials remain external runtime facts. W91 release evidence remains required; W92 additionally proves exact ZIP round-trip Apple trust; W93 then requires GitHub OIDC/Sigstore SLSA provenance for both exact native ZIPs, bound to this repository, signer workflow, release tag ref and source commit. Only the final W93 CI provenance authorization may unlock publication at tag runtime.",
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
