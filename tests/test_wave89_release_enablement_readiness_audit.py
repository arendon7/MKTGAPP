from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_enablement_audit.py"


def _module():
    spec = importlib.util.spec_from_file_location("wave89_release_enablement", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave89ReleaseEnablementReadinessAuditTests(unittest.TestCase):
    def test_current_source_is_explicitly_blocked_without_mutation(self):
        report = _module().audit(ROOT)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertIn("development_version", report["blocker_codes"])
        self.assertIn("release_flag_false", report["blocker_codes"])
        self.assertIn("release_tag_missing", report["blocker_codes"])
        self.assertFalse(report["mutations_performed"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["production_ready"])

    def test_all_w85_to_w88_structural_gates_are_present(self):
        report = _module().audit(ROOT)
        missing = [name for name, ok in report["structural_gates"].items() if not ok]
        self.assertEqual(missing, [], report)
        self.assertEqual(report["runtime_wave"], 76)
        self.assertGreaterEqual(report["certification_guard_wave"], 89)

    def test_audit_never_claims_external_runtime_evidence(self):
        report = _module().audit(ROOT)
        source = SCRIPT.read_text(encoding="utf-8")
        external = report["external_runtime_requirements"]
        self.assertIn("physical_uat_attestation_verified_at_tag_runtime", external)
        self.assertIn("apple_distribution_credentials_verified_at_tag_runtime", external)
        self.assertFalse(external["physical_uat_attestation_verified_at_tag_runtime"])
        self.assertFalse(external["apple_distribution_credentials_verified_at_tag_runtime"])
        self.assertFalse(report["operational_authorization"])
        self.assertIn("physical UAT", report["notes"])
        self.assertIn("external runtime fact", report["notes"])
        self.assertNotIn("RELEASE_READY = True", source)
        self.assertNotIn("gh release create", source)


if __name__ == "__main__":
    unittest.main()
