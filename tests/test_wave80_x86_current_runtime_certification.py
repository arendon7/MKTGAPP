import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Wave80X86CurrentRuntimeCertificationTests(unittest.TestCase):
    def test_persistent_workflow_has_native_intel_pull_request_gate(self):
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        self.assertIn("certify-current-runtime-x86:", workflow)
        self.assertIn("runs-on: macos-15-intel", workflow)
        self.assertIn("build_full_mac_release_candidate.sh --arch x86_64", workflow)
        self.assertIn("audit_wave80_x86_runtime_parity.sh", workflow)
        self.assertIn("WAVE 80 X86_64 W76 SMOKE PASS", workflow)

    def test_tag_release_jobs_remain_separate_from_pull_request_certification(self):
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        self.assertIn("if: github.event_name == 'pull_request'", workflow)
        self.assertIn("if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')", workflow)
        self.assertIn("RELEASE-arm64.json", workflow)
        self.assertIn("RELEASE-x86_64.json", workflow)

    def test_x86_builder_replays_exact_current_chain_instead_of_copying_it(self):
        x86 = (ROOT / "scripts/build_full_mac_current_x86_64.sh").read_text(encoding="utf-8")
        self.assertIn('SOURCE="$ROOT/scripts/build_full_mac_current.sh"', x86)
        self.assertIn("text.count(old) != 1", x86)
        self.assertIn("text.replace(old, new, 1)", x86)
        self.assertIn("requires a native Intel runner", x86)
        self.assertIn("service_wave76_app import serve", x86)
        self.assertNotIn("service_wave45_app import serve", x86)

    def test_x86_bundle_audit_preserves_arm64_only_physical_uat_boundary(self):
        audit = (ROOT / "scripts/audit_wave80_x86_runtime_parity.sh").read_text(encoding="utf-8")
        self.assertIn('provenance["architecture"] == "x86_64"', audit)
        self.assertIn('provenance["product_version"] == __version__ == "0.9.0"', audit)
        self.assertIn('source_release_state() == PREPARED_RELEASE', audit)
        self.assertIn('source_readiness["production_ready"] is False', audit)
        self.assertIn('"arm64-build" in preflight["blockers"]', audit)
        self.assertIn('ready_to_begin_physical_uat"] is False', audit)
        self.assertIn('dossier["stage"] == "BLOCKED_PREFLIGHT"', audit)
        self.assertIn("RELEASE_READY is True", audit)
        self.assertIn('RELEASE_TAG == "v0.9.0"', audit)

    def test_release_candidate_has_no_direct_historical_builder_fallback(self):
        candidate = (ROOT / "scripts/build_full_mac_release_candidate.sh").read_text(encoding="utf-8")
        self.assertIn("build_full_mac_current_x86_64.sh", candidate)
        self.assertIn("build_full_mac_current_guarded.sh", candidate)
        self.assertNotIn("build_full_mac_app.sh", candidate)
        self.assertIn("refusing historical fallback", candidate)


if __name__ == "__main__":
    unittest.main()
