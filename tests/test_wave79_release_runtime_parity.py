import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Wave79ReleaseRuntimeParityTests(unittest.TestCase):
    def test_persistent_release_never_calls_historical_base_builder_directly(self):
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        self.assertIn('build_full_mac_release_candidate.sh --arch', workflow)
        self.assertNotIn('scripts/build_full_mac_app.sh --arch', workflow)
        self.assertIn('service_wave76_app import serve', workflow)
        self.assertIn('"runtime_wave":76', workflow)
        self.assertIn('"certification_guard_wave":80', workflow)

    def test_release_candidate_routes_both_architectures_to_current_runtime_builders(self):
        builder = (ROOT / "scripts/build_full_mac_release_candidate.sh").read_text(encoding="utf-8")
        self.assertIn('build_full_mac_current_guarded.sh', builder)
        self.assertIn('build_full_mac_current_x86_64.sh', builder)
        self.assertIn('service_wave76_app import serve', builder)
        self.assertIn('refusing historical fallback', builder)
        self.assertNotIn('build_full_mac_app.sh', builder)

    def test_x86_64_current_builder_replays_canonical_chain_without_fallback(self):
        x86 = (ROOT / "scripts/build_full_mac_current_x86_64.sh").read_text(encoding="utf-8")
        self.assertIn('build_full_mac_current.sh', x86)
        self.assertIn('canonical current-builder architecture guard drifted', x86)
        self.assertIn('service_wave76_app import serve', x86)
        self.assertIn('audit_wave78_release_contract_drift_guard.sh', x86)
        self.assertIn('audit_wave80_x86_runtime_parity.sh', x86)
        self.assertNotIn('build_full_mac_app.sh', x86)

    def test_current_arm64_certification_runs_wave79_parity_audit(self):
        guarded = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        self.assertIn('audit_wave78_release_contract_drift_guard.sh', guarded)
        self.assertIn('audit_wave79_release_pipeline_parity.sh', guarded)
        self.assertIn('CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 79', guarded)


if __name__ == "__main__":
    unittest.main()
