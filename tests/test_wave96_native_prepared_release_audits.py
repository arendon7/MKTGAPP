import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Wave96NativePreparedReleaseAuditTests(unittest.TestCase):
    def test_w78_w79_w80_accept_prepared_source_without_production_authority(self):
        w78 = (ROOT / "scripts/audit_wave78_release_contract_drift_guard.sh").read_text(encoding="utf-8")
        w79 = (ROOT / "scripts/audit_wave79_release_pipeline_parity.sh").read_text(encoding="utf-8")
        w80 = (ROOT / "scripts/audit_wave80_x86_runtime_parity.sh").read_text(encoding="utf-8")
        for source in (w78, w79, w80):
            self.assertIn("PREPARED_RELEASE", source)
            self.assertIn("production_ready", source)
            self.assertNotIn('assert __version__ == "0.9.0.dev1"', source)
        self.assertIn('RELEASE_TAG == "v0.9.0"', w78)
        self.assertIn('RELEASE_TAG == "v0.9.0"', w79)
        self.assertIn('provenance["product_version"] == __version__ == "0.9.0"', w80)
        self.assertIn('"arm64-build" in preflight["blockers"]', w80)

    def test_w81_handoff_binds_prepared_identity_but_keeps_every_authority_false(self):
        audit = (ROOT / "scripts/audit_wave81_physical_uat_candidate_handoff.sh").read_text(encoding="utf-8")
        for marker in (
            "source_contract_wave']==95",
            "source_release_state",
            "operational_authorization'] is False",
            "release_authority'] is False",
            "publication_authority'] is False",
            "production_ready'] is False",
            "prepared_release_required_for_future_production",
        ):
            self.assertIn(marker, audit)
        self.assertIn("RELEASE_TAG == f'v{__version__}'", audit)
        self.assertNotIn("! /usr/bin/grep -q 'RELEASE_READY = True'", audit)

    def test_native_guard_chain_still_ends_at_wave81_without_changing_runtime_wave76(self):
        guarded = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        self.assertIn("audit_wave78_release_contract_drift_guard.sh", guarded)
        self.assertIn("audit_wave79_release_pipeline_parity.sh", guarded)
        self.assertIn("write_physical_uat_candidate.py", guarded)
        self.assertIn("audit_wave81_physical_uat_candidate_handoff.sh", guarded)
        self.assertIn("CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 81", guarded)
        self.assertNotIn("service_wave81_app", guarded)
        current = (ROOT / "scripts/build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave76_app import serve", current)


if __name__ == "__main__":
    unittest.main()
