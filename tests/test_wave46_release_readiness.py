import importlib.util
import unittest
from pathlib import Path

from binario_marketing.release_readiness import evaluate_release_readiness, source_release_readiness

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave46ReleaseReadinessTests(unittest.TestCase):
    def test_current_source_is_explicitly_development_blocked(self):
        report = source_release_readiness()
        self.assertEqual(report["stage"], "DEVELOPMENT")
        self.assertFalse(report["production_ready"])
        self.assertIn("development_version", report["blocker_codes"])
        self.assertIn("release_flag_false", report["blocker_codes"])
        self.assertIn("release_tag_missing", report["blocker_codes"])

    def test_full_production_contract_requires_every_gate(self):
        report = evaluate_release_readiness(
            version="1.0.0",
            release_ready=True,
            release_tag="v1.0.0",
            signing_mode="developer_id",
            notarized=True,
            uat_passed=True,
            git_sha="a" * 40,
            architecture="arm64",
        )
        self.assertEqual(report["stage"], "PRODUCTION_READY")
        self.assertTrue(report["production_ready"])
        self.assertEqual(report["blocker_codes"], [])

    def test_release_candidate_remains_blocked_without_distribution_and_uat(self):
        report = evaluate_release_readiness(
            version="1.0.0",
            release_ready=True,
            release_tag="v1.0.0",
            signing_mode="ad_hoc",
            notarized=False,
            uat_passed=False,
        )
        self.assertEqual(report["stage"], "RELEASE_CANDIDATE_BLOCKED")
        self.assertIn("distribution_signing_missing", report["blocker_codes"])
        self.assertIn("notarization_missing", report["blocker_codes"])
        self.assertIn("physical_uat_missing", report["blocker_codes"])

    def test_rc_or_dev_version_cannot_be_production_ready(self):
        for version in ("1.0.0rc1", "1.0.0-dev", "0.9.0.dev1", "1.0.0-beta"):
            with self.subTest(version=version):
                report = evaluate_release_readiness(
                    version=version,
                    release_ready=True,
                    release_tag="v1.0.0",
                    signing_mode="developer_id",
                    notarized=True,
                    uat_passed=True,
                )
                self.assertEqual(report["stage"], "DEVELOPMENT")
                self.assertFalse(report["production_ready"])
                self.assertIn("development_version", report["blocker_codes"])

    def test_gate_and_collector_are_fail_closed_and_sha_bound(self):
        gate = (ROOT / "scripts" / "release_candidate_gate.py").read_text(encoding="utf-8")
        collector = (ROOT / "scripts" / "collect_release_uat.py").read_text(encoding="utf-8")
        recorder = (ROOT / "scripts" / "record_release_uat.py").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_wave46_release_readiness.sh").read_text(encoding="utf-8")
        compile(gate, "release_candidate_gate.py", "exec")
        compile(collector, "collect_release_uat.py", "exec")
        compile(recorder, "record_release_uat.py", "exec")
        self.assertIn("data.get(\"git_sha\") != git_sha", gate)
        self.assertIn("embedded_source_state_matches", gate)
        self.assertIn('"uat_passed": False', collector)
        self.assertIn("automatic checks must pass", recorder)
        self.assertIn("BINARIO_CODESIGN_IDENTITY", builder)
        self.assertIn("RELEASE_READINESS.json", builder)
        self.assertIn("release-tools", builder)
        self.assertIn("audit_wave46_release_readiness.sh", builder)
        self.assertIn("physical_uat_missing", audit)
        self.assertIn("release_candidate_gate.py", audit)

    def test_uat_recorder_only_passes_when_every_manual_gate_passes(self):
        recorder = _load_script("wave46_uat_recorder", "record_release_uat.py")
        data = {
            "automatic_passed": True,
            "manual_steps": [
                {"id": "a", "status": "PASS"},
                {"id": "b", "status": "PENDING"},
            ],
        }
        recorder._recompute(data)
        self.assertFalse(data["uat_passed"])
        self.assertEqual(data["overall"], "AUTOMATIC_PASS_MANUAL_PENDING")
        data["manual_steps"][1]["status"] = "PASS"
        recorder._recompute(data)
        self.assertTrue(data["uat_passed"])
        self.assertEqual(data["overall"], "UAT_PASS")
        data["manual_steps"][0]["status"] = "FAIL"
        recorder._recompute(data)
        self.assertFalse(data["uat_passed"])
        self.assertEqual(data["overall"], "UAT_FAIL")

    def test_uat_evidence_schema_does_not_default_to_pass(self):
        collector = (ROOT / "scripts" / "collect_release_uat.py").read_text(encoding="utf-8")
        self.assertIn('SCHEMA = "binario.marketing.release-uat-evidence.v1"', collector)
        self.assertIn('"overall": "AUTOMATIC_FAIL" if not automatic_ok else "AUTOMATIC_PASS_MANUAL_PENDING"', collector)
        self.assertNotIn('"uat_passed": True', collector)


if __name__ == "__main__":
    unittest.main()
