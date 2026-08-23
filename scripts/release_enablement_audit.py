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
    physical_writer = (repo / "scripts/write_physical_uat_candidate.py").read_text(encoding="utf-8")
    release_contract = (repo / "src/binario_marketing/release_contract.py").read_text(encoding="utf-8")
    workflow_names = sorted(path.name for path in (repo / ".github/workflows").glob("*.yml"))

    prepared_index = workflow.find("verify_prepared_release_uat.py")
    distribution_index = workflow.find("build_full_mac_release_candidate.sh --distribution")
    structural = {
        "physical_uat_attestation_transport": "verify_combined_uat_attestation.py" in workflow and "PHYSICAL_UAT_ATTESTATION_B64" in workflow,
        "prepared_release_source_contract": "PREPARED_RELEASE" in release_contract and "LOCKED_SOURCE" in release_contract and "same_commit_must_be_tagged" in release_contract,
        "prepared_release_physical_uat_gate": prepared_index != -1 and distribution_index != -1 and prepared_index < distribution_index and "--expected-git-sha" in workflow and "--expected-tag" in workflow,
        "exact_physical_candidate_is_main_only": 'ref == "refs/heads/main"' in physical_writer and "Tag builds are source-equivalent distribution rebuilds" in physical_writer,
        "developer_id_credentials_gate": "APPLE_DEVELOPER_ID_P12_BASE64" in workflow and "BINARIO_CODESIGN_IDENTITY" in workflow,
        "notarization_gate": "notarize_release_candidate.sh" in workflow and "verify_distribution_trust.py" in workflow,
        "distribution_rebuild_identity": "DISTRIBUTION_REBUILD.json" in gate and "binario.marketing.distribution-rebuild.v1" in distribution_writer,
        "production_gate_before_packaging": workflow.find("release_candidate_gate.py") != -1 and workflow.find("Package immutable release asset") != -1 and workflow.find("release_candidate_gate.py") < workflow.find("Package immutable release asset"),
        "release_tag_verifier": "verify_release_tag.py" in workflow and "verify_pipeline_contract" in tag_verifier and "verify_prepared_release_uat.py" in tag_verifier,
        "runtime_wave_76_preserved": '"runtime_wave":76' in workflow or "runtime_wave\":76" in workflow,
        "canonical_workflow_count": workflow_names == ["ci.yml", "full-mac-app.yml", "persistent-release.yml"],
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
        "prepared_release_contract": {
            "stable_version_required": True,
            "canonical_tag_required_before_physical_uat": True,
            "same_commit_must_be_physically_tested_then_tagged": True,
            "source_readiness_is_release_authority": False,
        },
        "operational_authorization": False,
        "mutations_performed": False,
        "release_authority": False,
        "production_ready": False,
        "notes": "Source readiness never authorizes release. Wave 91 additionally requires the stable canonical tag contract to exist before physical UAT so the exact tested commit can later be tagged without source mutation. Physical UAT evidence, Apple credentials, Developer ID signing, notarization, distribution rebuild verification and the production gate still must all pass at tag runtime.",
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
