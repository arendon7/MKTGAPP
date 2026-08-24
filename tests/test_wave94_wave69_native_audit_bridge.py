from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_wave69_physical_uat_preflight.sh"
SERVICE = ROOT / "src" / "binario_marketing" / "service_wave69_app.py"


class Wave94Wave69NativeAuditBridgeTests(unittest.TestCase):
    def test_native_w69_audit_tracks_structured_w94_contract_not_legacy_literal(self):
        audit = AUDIT.read_text(encoding="utf-8")
        service = SERVICE.read_text(encoding="utf-8")

        # The historical free-form marker was removed by W94. Native certification
        # must follow the actual machine-verifiable contract instead of requiring
        # a decorative source string merely to satisfy grep.
        self.assertNotIn("grep -q 'release-fail-closed'", audit)

        required_markers = (
            "LOCKED_SOURCE",
            "PREPARED_RELEASE",
            "source_release_state",
            "refs/heads/main",
            "signing_mode.*ad_hoc",
            "notarized.*False",
            '"operational_authorization": False',
            '"release_authority": False',
            '"publication_authority": False',
            '"production_ready": False',
            "physical_preflight_is_release_authority",
        )
        for marker in required_markers:
            with self.subTest(marker=marker):
                self.assertIn(marker, audit)

        # Every semantic source marker that the shell audit relies upon must also
        # be present in the current W69 implementation. Regex-style shell markers
        # are represented by their underlying semantic tokens here.
        for marker in (
            "LOCKED_SOURCE",
            "PREPARED_RELEASE",
            "source_release_state",
            "refs/heads/main",
            "signing_mode",
            "ad_hoc",
            "notarized",
            '"operational_authorization": False',
            '"release_authority": False',
            '"publication_authority": False',
            '"production_ready": False',
            "physical_preflight_is_release_authority",
        ):
            with self.subTest(service_marker=marker):
                self.assertIn(marker, service)

    def test_w69_audit_still_preserves_read_only_browser_boundary(self):
        audit = AUDIT.read_text(encoding="utf-8")
        for forbidden in ("method:'POST'", "method:'PATCH'", "setInterval", "sendBeacon"):
            self.assertIn(f"! /usr/bin/grep", audit)
            self.assertIn(forbidden, audit)
        self.assertIn("supabase\\|vercel", audit)
        self.assertIn("WAVE 69 PHYSICAL UAT PREFLIGHT AUDIT PASS", audit)


if __name__ == "__main__":
    unittest.main()
