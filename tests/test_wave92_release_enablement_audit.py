from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "release_enablement_audit.py"
ROUNDTRIP = ROOT / "scripts" / "verify_packaged_release_asset.py"
AUTH = ROOT / "scripts" / "release_artifact_authorization.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"
PUBLISHER = ROOT / "scripts" / "publish_release_transaction.sh"
VERSION = ROOT / "src" / "binario_marketing" / "version.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave92ReleaseEnablementAuditTests(unittest.TestCase):
    def test_current_source_remains_blocked_and_has_no_publication_authority(self):
        report = _module(AUDIT, "w92_audit_blocked").audit(ROOT)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["source_status"], "BLOCKED")
        self.assertEqual(report["runtime_wave"], 76)
        self.assertGreaterEqual(report["certification_guard_wave"], 92)
        self.assertFalse(report["operational_authorization"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["publication_authority"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["mutations_performed"])
        self.assertIn("development_version", report["blocker_codes"])
        self.assertIn("release_flag_false", report["blocker_codes"])
        self.assertIn("release_tag_missing", report["blocker_codes"])

    def test_all_w92_structural_gates_are_present(self):
        report = _module(AUDIT, "w92_audit_structure").audit(ROOT)
        missing = [name for name, value in report["structural_gates"].items() if value is not True]
        self.assertEqual(missing, [], report)
        for name in (
            "post_package_roundtrip_schema",
            "post_package_roundtrip_after_packaging",
            "post_package_roundtrip_before_native_artifact_upload",
            "post_package_roundtrip_apple_trust_checks",
            "post_package_roundtrip_is_non_authoritative",
            "w92_artifact_authorization_schema",
            "w92_authorization_after_w91",
            "w92_authorization_after_roundtrip_verification",
            "w92_final_authorization_verification_before_publish",
            "w92_artifact_authorization_manifest_required_for_publish",
        ):
            self.assertTrue(report["structural_gates"][name], name)

    def test_external_runtime_truth_is_never_inferred_from_source(self):
        report = _module(AUDIT, "w92_audit_external").audit(ROOT)
        external = report["external_runtime_requirements"]
        for name in (
            "post_package_roundtrip_trust_verified_for_arm64_at_tag_runtime",
            "post_package_roundtrip_trust_verified_for_x86_64_at_tag_runtime",
            "w92_artifact_publication_authorization_verified_at_tag_runtime",
        ):
            self.assertIn(name, external)
            self.assertFalse(external[name])
        self.assertIn("W91", report["notes"])
        self.assertIn("W92", report["notes"])
        self.assertIn("round-trip", report["notes"])

    def test_w91_remains_necessary_but_is_not_the_last_publication_gate(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        publisher = PUBLISHER.read_text(encoding="utf-8")
        w91_verify = workflow.index("Verify final W91 release authorization")
        w92_build = workflow.index("Build W92 artifact publication authorization")
        w92_verify = workflow.index("Verify W92 final publication authorization")
        publish = workflow.index("publish_release_transaction.sh")
        self.assertLess(w91_verify, w92_build)
        self.assertLess(w92_build, w92_verify)
        self.assertLess(w92_verify, publish)
        self.assertIn("test -f release/RELEASE-ARTIFACT-AUTHORIZATION.json", publisher)

    def test_post_package_evidence_cannot_self_grant_release_authority(self):
        source = ROUNDTRIP.read_text(encoding="utf-8")
        self.assertIn('"operational_authorization": False', source)
        self.assertIn('"release_authority": False', source)
        self.assertIn('"publication_authority": False', source)
        self.assertIn('"production_ready": False', source)

    def test_final_w92_authorizer_requires_w91_and_both_architectures(self):
        source = AUTH.read_text(encoding="utf-8")
        self.assertIn('w91.get("release_authority") is True', source)
        self.assertIn('architecture="arm64"', source)
        self.assertIn('architecture="x86_64"', source)
        self.assertIn("both_developer_id_signatures_survive_roundtrip", source)
        self.assertIn("both_notarization_tickets_survive_roundtrip", source)
        self.assertIn("both_gatekeeper_assessments_pass_after_roundtrip", source)

    def test_release_boundary_and_workflow_count_remain_closed(self):
        version = VERSION.read_text(encoding="utf-8")
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
