#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state  # noqa: E402
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__  # noqa: E402

SCHEMA = "binario.marketing.prepared-release-source-audit.v1"
CERTIFICATION_GUARD_WAVE = 96
SOURCE_CONTRACT_WAVE = 95
EXPECTED_VERSION = "0.9.0"
EXPECTED_TAG = "v0.9.0"
EXPECTED_WORKFLOWS = ["ci.yml", "full-mac-app.yml", "persistent-release.yml"]


def _load_release_enablement_audit(repo: Path):
    path = repo / "scripts" / "release_enablement_audit.py"
    spec = importlib.util.spec_from_file_location("wave96_release_enablement", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def audit(repo: Path = ROOT) -> dict[str, Any]:
    repo = repo.resolve()
    readiness = source_release_readiness()
    state = source_release_state()
    generic = _load_release_enablement_audit(repo).audit(repo)
    workflow = (repo / ".github" / "workflows" / "persistent-release.yml").read_text(encoding="utf-8")
    candidate_writer = (repo / "scripts" / "write_physical_uat_candidate.py").read_text(encoding="utf-8")
    gate = (repo / "scripts" / "release_candidate_gate.py").read_text(encoding="utf-8")
    version_source = (repo / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
    workflows = sorted(path.name for path in (repo / ".github" / "workflows").glob("*.yml"))

    checks = {
        "canonical_version_is_v0_9_0": __version__ == EXPECTED_VERSION,
        "release_flag_marks_prepared_source": RELEASE_READY is True,
        "canonical_release_tag_is_v0_9_0": RELEASE_TAG == EXPECTED_TAG,
        "source_state_is_prepared_release": state == PREPARED_RELEASE,
        "source_readiness_is_ready_only": readiness.get("source_ready") is True
        and readiness.get("stage") == "SOURCE_CONTRACT_READY"
        and readiness.get("operational_inputs_complete") is False,
        "source_readiness_is_not_production": readiness.get("production_ready") is False,
        "generic_audit_has_no_source_blockers": generic.get("source_status") == "SOURCE_CONTRACT_READY"
        and generic.get("status") == "AWAITING_OPERATIONAL_AUTHORIZATION"
        and generic.get("blocker_codes") == [],
        "generic_audit_grants_no_authority": all(
            generic.get(name) is False
            for name in (
                "operational_authorization",
                "release_authority",
                "publication_authority",
                "production_ready",
                "mutations_performed",
            )
        ),
        "external_runtime_requirements_remain_unproven": bool(generic.get("external_runtime_requirements"))
        and all(value is False for value in generic["external_runtime_requirements"].values()),
        "physical_candidate_remains_main_push_only": 'event == "push"' in candidate_writer
        and 'ref == "refs/heads/main"' in candidate_writer
        and "SOURCE_CONTRACT_WAVE = 95" in candidate_writer,
        "production_gate_still_requires_prepared_physical_uat": all(
            marker in gate
            for marker in (
                "prepared_release_uat_required",
                "prepared_release_tag_mismatch",
                "prepared_release_source_required",
                "EXPECTED_SOURCE_CONTRACT_WAVE = 95",
            )
        ),
        "tag_workflow_still_requires_prepared_uat": "--expected-source-release-state PREPARED_RELEASE" in workflow
        and '--expected-release-tag "$GITHUB_REF_NAME"' in workflow,
        "tag_jobs_remain_tag_scoped": "startsWith(github.ref, 'refs/tags/v')" in workflow,
        "exactly_three_canonical_workflows": workflows == EXPECTED_WORKFLOWS,
        "version_source_has_no_authority_claim": all(
            marker not in version_source
            for marker in (
                "operational_authorization = True",
                "release_authority = True",
                "publication_authority = True",
                "production_ready = True",
            )
        ),
    }

    failures = [name for name, ok in checks.items() if not ok]
    return {
        "schema": SCHEMA,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "source_contract_wave": SOURCE_CONTRACT_WAVE,
        "runtime_wave": 76,
        "version": __version__,
        "release_tag": RELEASE_TAG,
        "source_release_state": state,
        "status": "PREPARED_FOR_PHYSICAL_UAT" if not failures else "BLOCKED",
        "checks": checks,
        "failure_codes": failures,
        "physical_uat_required": True,
        "operational_authorization": False,
        "release_authority": False,
        "publication_authority": False,
        "production_ready": False,
        "mutations_performed": False,
        "note": (
            "Wave 96 freezes v0.9.0/v0.9.0 before physical UAT. This source state is not release authority. "
            "The exact eligible arm64 candidate must still be produced by a controlled push to main and then "
            "pass real physical UAT before the tag release path can consume its attestation."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Wave 96 prepared release source without granting release authority.")
    parser.add_argument("--repo", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    report = audit(args.repo)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if report["status"] == "PREPARED_FOR_PHYSICAL_UAT" else 3


if __name__ == "__main__":
    raise SystemExit(main())
