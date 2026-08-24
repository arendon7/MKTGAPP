from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.release_readiness import (
    LOCKED_SOURCE,
    PREPARED_RELEASE,
    evaluate_release_readiness,
    source_release_state,
)
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "release_enablement_audit.py"
WRITER = ROOT / "scripts" / "write_physical_uat_candidate.py"
COMBINED = ROOT / "scripts" / "verify_combined_uat_attestation.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave95PreparedReleaseShaStabilityTests(unittest.TestCase):
    def test_source_contract_has_only_locked_or_prepared_states(self):
        self.assertEqual(
            source_release_state(version="0.9.0.dev1", release_ready=False, release_tag=None),
            LOCKED_SOURCE,
        )
        self.assertEqual(
            source_release_state(version="1.0.0", release_ready=True, release_tag="v1.0.0"),
            PREPARED_RELEASE,
        )
        invalid = (
            ("1.0.0", False, "v1.0.0"),
            ("1.0.0", True, None),
            ("1.0.0", True, "v1.0.1"),
            ("1.0.0.dev1", True, "v1.0.0.dev1"),
            ("1.0.0rc1", True, "v1.0.0rc1"),
        )
        for version, ready, tag in invalid:
            with self.subTest(version=version, ready=ready, tag=tag), self.assertRaises(ValueError):
                source_release_state(version=version, release_ready=ready, release_tag=tag)

    def test_prepared_source_without_operational_inputs_is_not_production(self):
        report = evaluate_release_readiness(
            version="1.0.0",
            release_ready=True,
            release_tag="v1.0.0",
        )
        self.assertEqual(report["source_release_state"], PREPARED_RELEASE)
        self.assertTrue(report["source_ready"])
        self.assertFalse(report["operational_inputs_complete"])
        self.assertEqual(report["stage"], "SOURCE_CONTRACT_READY")
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["blocker_codes"], [])

    def test_production_readiness_requires_all_operational_facts_explicitly(self):
        ready = evaluate_release_readiness(
            version="1.0.0",
            release_ready=True,
            release_tag="v1.0.0",
            signing_mode="developer_id",
            notarized=True,
            uat_passed=True,
            git_sha="a" * 40,
            architecture="arm64",
        )
        self.assertEqual(ready["stage"], "PRODUCTION_READY")
        self.assertTrue(ready["operational_inputs_complete"])
        self.assertTrue(ready["production_ready"])

        blocked = evaluate_release_readiness(
            version="1.0.0",
            release_ready=True,
            release_tag="v1.0.0",
            signing_mode="developer_id",
            notarized=True,
            uat_passed=False,
        )
        self.assertFalse(blocked["production_ready"])
        self.assertIn("physical_uat_missing", blocked["blocker_codes"])

    def test_exact_physical_candidate_origin_is_main_only(self):
        writer = _module(WRITER, "w95_writer")
        self.assertTrue(writer._trusted_origin("push", "refs/heads/main"))
        self.assertFalse(writer._trusted_origin("push", "refs/tags/v1.0.0"))
        self.assertFalse(writer._trusted_origin("pull_request", "refs/pull/105/merge"))
        self.assertEqual(writer.SOURCE_CONTRACT_WAVE, 95)

    def test_prepared_combined_uat_requires_wave95_and_exact_release_tag(self):
        verifier = _module(COMBINED, "w95_combined")
        binding = {
            "git_sha": "a" * 40,
            "product_version": "1.0.0",
            "architecture": "arm64",
            "runtime_wave": 76,
            "candidate_guard_wave": 84,
            "certification_guard_wave": 84,
            "source_contract_wave": 95,
            "source_release_state": PREPARED_RELEASE,
            "source_release_tag": "v1.0.0",
            "candidate_source_sha256": "b" * 64,
            "candidate_manifest_sha256": "c" * 64,
        }
        handoff = {
            "schema": verifier.W97_HANDOFF_SCHEMA,
            "git_sha": binding["git_sha"],
            "role": "PHYSICAL_UAT_CANDIDATE_ONLY",
            "physical_uat_eligible": True,
            "architecture": "arm64",
            "runtime_wave": 76,
            "source_contract_wave": 95,
            "source_release_state": PREPARED_RELEASE,
            "source_release_tag": "v1.0.0",
            "candidate_source_sha256": binding["candidate_source_sha256"],
            "actual_candidate_source_sha256": binding["candidate_source_sha256"],
            "candidate_manifest_sha256": binding["candidate_manifest_sha256"],
            "host": {
                "system": "Darwin",
                "machine": "arm64",
                "is_ci": False,
                "physical_gate_eligible": True,
            },
        }
        core = {
            "schema": verifier.SCHEMA,
            "binding": binding,
            "phase_a": {"required_scenarios": 5, "passed_scenarios": 5},
            "phase_b": {"required_gates": 12, "passed_gates": 12, "overall": "UAT_PASS"},
            "w97_integrity": {
                "schema": verifier.W97_INTEGRITY_SCHEMA,
                "handoff_verification_sha256": "9" * 64,
                "handoff_verification": handoff,
                "bundle_signature_verified": True,
                "codesign_requirement": ["--deep", "--strict"],
                "source_digest_reverified": True,
                "physical_host_reverified": True,
            },
            "both_phases_passed": True,
            "release_authority": False,
            "publication_authority": False,
            "production_ready": False,
        }
        payload = {**core, "generated_at": "2026-08-23T00:00:00+00:00", "attestation_sha256": verifier._digest(core)}
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "combined.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            report = verifier.verify(
                path,
                expected_git_sha="a" * 40,
                expected_source_release_state=PREPARED_RELEASE,
                expected_release_tag="v1.0.0",
            )
            self.assertEqual(report["source_contract_wave"], 95)
            self.assertEqual(report["source_release_state"], PREPARED_RELEASE)
            self.assertEqual(report["source_release_tag"], "v1.0.0")
            self.assertTrue(report["w97_integrity_required"])
            self.assertTrue(report["w97_integrity_verified"])
            self.assertEqual(report["w97_handoff_verification_sha256"], "9" * 64)
            self.assertFalse(report["release_authority"])
            self.assertFalse(report["publication_authority"])
            self.assertFalse(report["production_ready"])

            with self.assertRaisesRegex(ValueError, "release tag mismatch"):
                verifier.verify(
                    path,
                    expected_source_release_state=PREPARED_RELEASE,
                    expected_release_tag="v1.0.1",
                )

            payload["binding"]["source_contract_wave"] = 94
            core_old = dict(core)
            core_old["binding"] = dict(payload["binding"])
            payload["attestation_sha256"] = verifier._digest(core_old)
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "W95 source contract"):
                verifier.verify(path, expected_source_release_state=PREPARED_RELEASE)

    def test_workflow_requires_prepared_uat_before_w91_w92_w94_w93_chain(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertGreaterEqual(workflow.count("--expected-source-release-state PREPARED_RELEASE"), 2)
        self.assertGreaterEqual(workflow.count('--expected-release-tag "$GITHUB_REF_NAME"'), 2)
        self.assertIn("from binario_marketing.version import __version__", workflow)
        self.assertIn("row['product_version']==__version__", workflow)
        self.assertNotIn("row['product_version']=='0.9.0.dev1'", workflow)

        preflight = workflow.index("Decode and verify exact physical UAT attestation")
        production_gate = workflow.index("Enforce and persist production release candidate gate")
        package = workflow.index("Package immutable release asset")
        roundtrip = workflow.index("Verify W92 packaged artifact round-trip trust")
        w91 = workflow.index("Build cross-architecture release authorization")
        w92 = workflow.index("Build W92 artifact publication authorization")
        w94 = workflow.index("Build W94 CI provenance transaction handoff")
        w93 = workflow.index("run: bash scripts/publish_release_transaction.sh")
        self.assertLess(preflight, production_gate)
        self.assertLess(production_gate, package)
        self.assertLess(package, roundtrip)
        self.assertLess(roundtrip, w91)
        self.assertLess(w91, w92)
        self.assertLess(w92, w94)
        self.assertLess(w94, w93)

    def test_w94_oidc_provenance_and_w93_transaction_are_preserved(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        publisher = (ROOT / "scripts/publish_release_transaction.sh").read_text(encoding="utf-8")
        self.assertIn("uses: actions/attest@v4.2.1", workflow)
        self.assertIn("id-token: write", workflow)
        self.assertIn("attestations: write", workflow)
        self.assertIn("artifact-metadata: write", workflow)
        self.assertIn("CI-PROVENANCE-${{ matrix.arch }}.sigstore.json", workflow)
        self.assertIn("release_ci_provenance_authorization.py authorize", workflow)
        self.assertIn("release_ci_provenance_authorization.py verify-authorization", workflow)
        self.assertIn("W94_STAGE_PROVENANCE_HANDOFF", publisher)
        self.assertIn("W93_STAGE_DRAFT_CREATE", publisher)
        self.assertLess(publisher.index("W94_STAGE_PROVENANCE_HANDOFF"), publisher.index("W93_STAGE_DRAFT_CREATE"))

    def test_release_enablement_audit_preserves_w91_to_w94_and_adds_w95(self):
        report = _module(AUDIT, "w95_audit").audit(ROOT)
        self.assertEqual(report["schema"], "binario.marketing.release-enablement-audit.v7")
        self.assertEqual(report["runtime_wave"], 76)
        self.assertEqual(report["certification_guard_wave"], 95)
        self.assertEqual(report["source_contract_wave"], 95)
        self.assertEqual(report["source_release_state"], PREPARED_RELEASE)
        self.assertEqual(report["status"], "AWAITING_OPERATIONAL_AUTHORIZATION")
        self.assertEqual(report["source_status"], "SOURCE_CONTRACT_READY")
        self.assertEqual(report["blocker_codes"], [])
        self.assertFalse(report["operational_authorization"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["publication_authority"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["mutations_performed"])
        self.assertTrue(all(value is False for value in report["external_runtime_requirements"].values()))
        missing = [name for name, ok in report["structural_gates"].items() if ok is not True]
        self.assertEqual(missing, [], report)
        for gate in (
            "w91_cross_arch_release_authorization_before_publish",
            "post_package_roundtrip_schema",
            "w92_artifact_authorization_schema",
            "w93_publication_is_transactional",
            "w94_provenance_action_pinned",
            "w94_transaction_handoff_precedes_any_w93_mutation",
            "w95_two_state_source_contract",
            "w95_source_contract_generation_is_95",
            "w95_exact_physical_candidate_is_main_only",
            "w95_production_requires_prepared_uat",
            "w95_tag_preflight_binds_prepared_uat",
            "w95_intel_smoke_uses_canonical_version",
            "w95_prepared_source_remains_non_authoritative",
            "w95_preserves_w94_before_w93",
        ):
            self.assertTrue(report["structural_gates"][gate], gate)

    def test_current_repository_may_be_prepared_without_release_authority(self):
        self.assertEqual(__version__, "0.9.0")
        self.assertTrue(RELEASE_READY)
        self.assertEqual(RELEASE_TAG, "v0.9.0")
        self.assertEqual(source_release_state(), PREPARED_RELEASE)
        readiness = evaluate_release_readiness()
        self.assertTrue(readiness["source_ready"])
        self.assertEqual(readiness["stage"], "SOURCE_CONTRACT_READY")
        self.assertFalse(readiness["operational_inputs_complete"])
        self.assertFalse(readiness["production_ready"])
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])

    def test_phase_b_handoff_and_distribution_bind_same_w95_source_contract(self):
        files = {
            "collector": ROOT / "scripts/collect_release_uat.py",
            "recorder": ROOT / "scripts/record_release_uat.py",
            "finalizer": ROOT / "scripts/finalize_physical_uat.py",
            "handoff": ROOT / "scripts/verify_physical_uat_handoff.py",
            "packager": ROOT / "scripts/package_current_arm64_candidate.py",
            "distribution": ROOT / "scripts/write_distribution_rebuild_manifest.py",
        }
        for name, path in files.items():
            with self.subTest(name=name):
                source = path.read_text(encoding="utf-8")
                self.assertIn("95", source)
                self.assertIn("PREPARED_RELEASE", source)
                self.assertIn("LOCKED_SOURCE", source)


if __name__ == "__main__":
    unittest.main()
