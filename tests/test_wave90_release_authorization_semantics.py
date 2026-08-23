from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_enablement_audit.py"


def _module():
    spec = importlib.util.spec_from_file_location("wave90_release_audit", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave90ReleaseAuthorizationSemanticsTests(unittest.TestCase):
    def test_current_source_remains_blocked_without_release_mutation(self):
        report = _module().audit(ROOT)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["operational_authorization"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["production_ready"])
        self.assertIn("development_version", report["blocker_codes"])
        self.assertIn("release_flag_false", report["blocker_codes"])
        self.assertIn("release_tag_missing", report["blocker_codes"])

    def test_source_ready_state_never_becomes_release_authority(self):
        module = _module()
        with mock.patch.object(module, "_load_version", return_value=("1.0.0", True, "v1.0.0")):
            report = module.audit(ROOT)
        self.assertEqual(report["source_status"], "SOURCE_CONTRACT_READY")
        self.assertEqual(report["status"], "AWAITING_OPERATIONAL_AUTHORIZATION")
        self.assertFalse(report["operational_authorization"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(any(report["external_runtime_requirements"].values()))

    def test_external_runtime_gates_are_explicit_and_not_inferred_from_source(self):
        report = _module().audit(ROOT)
        required = {
            "physical_uat_attestation_verified_at_tag_runtime",
            "apple_distribution_credentials_verified_at_tag_runtime",
            "developer_id_signature_verified_at_tag_runtime",
            "apple_notarization_verified_at_tag_runtime",
            "distribution_rebuild_verified_at_tag_runtime",
            "production_gate_passed_at_tag_runtime",
        }
        self.assertEqual(set(report["external_runtime_requirements"]), required)
        self.assertTrue(all(value is False for value in report["external_runtime_requirements"].values()))


if __name__ == "__main__":
    unittest.main()
