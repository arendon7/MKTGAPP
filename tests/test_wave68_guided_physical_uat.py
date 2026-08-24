import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave68_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave68GuidedPhysicalUATTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_guidance_reuses_wave66_manual_scenario_contract(self):
        overview = self.runtime.physical_uat_overview(self.company["id"])
        scenarios = overview["readiness"]["manual_scenarios"]
        self.assertGreaterEqual(len(scenarios), 6)
        for row in scenarios:
            self.assertTrue(row["id"])
            self.assertTrue(row["view"])
            self.assertTrue(row["precondition"])
            self.assertTrue(row["expected"])

    def test_http_chains_wave68_after_strict_wave67_surface(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/physical-uat.js", timeout=5) as response:
                body = response.read().decode("utf-8")
            self.assertIn("Evidencia de prueba en Mac físico", body)
            self.assertIn("guided-physical-uat.js", body)
            self.assertIn("data-guided-physical-uat-wave68", body)
            with urlopen(base + "/guided-physical-uat.js", timeout=5) as response:
                guided = response.read().decode("utf-8")
            self.assertIn("PRECONDICIÓN", guided)
            self.assertIn("RESULTADO ESPERADO", guided)
            self.assertIn("Abrir módulo", guided)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_guided_layer_never_records_evidence_or_marketing_actions(self):
        ui = (ROOT / "web" / "guided-physical-uat.js").read_text(encoding="utf-8")
        for marker in ("wave67State.overview", "manual_scenarios", "wave68Open", "wave67Scenario", "wave67Panel"):
            self.assertIn(marker, ui)
        for forbidden in ("method:'POST'", "method:'PATCH'", "setInterval", "sendBeacon", "/opportunities", "/publications", "/paid-media", "/ai/generate", "supabase", "vercel"):
            self.assertNotIn(forbidden, ui.lower() if forbidden in {"supabase", "vercel"} else ui)

    def test_progress_is_derived_only_from_manual_session_statuses(self):
        ui = (ROOT / "web" / "guided-physical-uat.js").read_text(encoding="utf-8")
        for status in ("PASS", "FAIL", "BLOCKED", "PENDING"):
            self.assertIn(status, ui)
        self.assertNotIn("physical_uat_complete=true", ui)
        self.assertNotIn("RELEASE_READY", ui)

    def test_builder_runs_w67_audit_before_injecting_w68(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave67_app import serve", builder)
        self.assertIn("service_wave68_app import serve", builder)
        self.assertIn("audit_wave67_physical_uat_harness.sh", builder)
        self.assertIn("audit_wave68_guided_physical_uat.sh", builder)
        self.assertLess(builder.index("audit_wave67_physical_uat_harness.sh"), builder.index("service_wave68_app import serve"))
        for wave in (59, 60, 61, 62, 63, 64, 65, 66, 67, 68):
            self.assertIn(f"CURRENT ARM64 ITERATION BUILD PASS: Wave {wave}", builder)

    def test_release_and_workflow_contracts_remain_fail_closed(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        self.assertEqual(source_release_state(), PREPARED_RELEASE)
        report = source_release_readiness()
        self.assertTrue(report["source_ready"])
        self.assertEqual(report["stage"], "SOURCE_CONTRACT_READY")
        self.assertFalse(report["operational_inputs_complete"])
        self.assertFalse(report["production_ready"])
        audit = (ROOT / "scripts" / "audit_wave68_guided_physical_uat.sh").read_text(encoding="utf-8")
        self.assertIn("WAVE 68 GUIDED PHYSICAL UAT AUDIT PASS", audit)


if __name__ == "__main__":
    unittest.main()
