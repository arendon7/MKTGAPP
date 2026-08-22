import subprocess
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
        self.assertIn('"certification_guard_wave":78', workflow)

    def test_release_candidate_arm64_routes_to_current_guarded_builder(self):
        builder = (ROOT / "scripts/build_full_mac_release_candidate.sh").read_text(encoding="utf-8")
        self.assertIn('build_full_mac_current_guarded.sh', builder)
        self.assertIn('service_wave76_app import serve', builder)
        self.assertIn('refusing to fall back to the historical W45 base builder', builder)

    def test_x86_64_release_candidate_fails_closed_before_historical_fallback(self):
        proc = subprocess.run(
            ["bash", str(ROOT / "scripts/build_full_mac_release_candidate.sh"), "--arch", "x86_64"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 4, proc.stdout + proc.stderr)
        self.assertIn("not yet certified for x86_64", proc.stderr)
        self.assertIn("refusing to fall back", proc.stderr)

    def test_current_arm64_certification_runs_wave79_parity_audit(self):
        guarded = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        self.assertIn('audit_wave78_release_contract_drift_guard.sh', guarded)
        self.assertIn('audit_wave79_release_pipeline_parity.sh', guarded)
        self.assertIn('CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 79', guarded)


if __name__ == "__main__":
    unittest.main()
