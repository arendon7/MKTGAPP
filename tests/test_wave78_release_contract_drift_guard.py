import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _compact(text: str) -> str:
    return "".join(text.split())


class Wave78ReleaseContractDriftGuardTests(unittest.TestCase):
    def test_physical_uat_preflight_key_is_canonical_end_to_end(self):
        wave69 = (ROOT / "src/binario_marketing/service_wave69_app.py").read_text(encoding="utf-8")
        wave71 = (ROOT / "src/binario_marketing/service_wave71_app.py").read_text(encoding="utf-8")
        self.assertIn('"ready_to_begin_physical_uat":ready', _compact(wave69))
        self.assertIn('preflight.get("ready_to_begin_physical_uat")', wave71)
        self.assertNotIn('preflight.get("ready_for_physical_uat")', wave71)

    def test_bundle_guard_checks_the_contract_and_release_boundary(self):
        audit = (ROOT / "scripts/audit_wave78_release_contract_drift_guard.sh").read_text(encoding="utf-8")
        self.assertIn('ready_to_begin_physical_uat', audit)
        self.assertIn('ready_for_physical_uat', audit)
        self.assertIn('RELEASE_READY is False', audit)
        self.assertIn('RELEASE_TAG is None', audit)
        self.assertIn('READY_FOR_PHYSICAL_UAT', audit)
        self.assertIn('BLOCKED_PREFLIGHT', audit)
        self.assertIn('functional-only', audit)

    def test_full_mac_compatibility_entrypoint_runs_wave78_guard(self):
        wrapper = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        shim = (ROOT / "scripts/build_full_mac_wave47.sh").read_text(encoding="utf-8")
        self.assertIn('build_full_mac_current.sh', wrapper)
        self.assertIn('audit_wave78_release_contract_drift_guard.sh', wrapper)
        self.assertIn('build_full_mac_current_guarded.sh', shim)

    def test_wave78_does_not_replace_current_wave76_runtime(self):
        wrapper = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        current = (ROOT / "scripts/build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertNotIn('service_wave78_app', wrapper)
        self.assertNotIn('service_wave78_app', current)
        self.assertIn('service_wave76_app import serve', current)
        self.assertIn('CURRENT ARM64 ITERATION BUILD PASS: Wave 76', current)


if __name__ == "__main__":
    unittest.main()
