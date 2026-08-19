import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service_wave66_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave66ProductUATReadinessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _campaign(self, name="Campaña W66"):
        return self.runtime.create_campaign(self.company["id"], {
            "name": name,
            "objective": "LEADS",
            "status": "IN_PROGRESS",
            "channels": ["facebook_page", "instagram"],
        })

    def _snapshot(self, campaign):
        return self.runtime.learning.create_snapshot(self.company["id"], {
            "date_preset": "last_7d",
            "social": {
                "coverage": {"eligible": 1, "requested": 1, "measured": 1, "errors": 0},
                "totals": {"reach": 100, "total_interactions": 12},
                "observations": [{
                    "campaign_id": campaign["id"],
                    "creative_media_id": None,
                    "metrics": {"reach": 100, "total_interactions": 12},
                }],
            },
            "paid_media": {
                "coverage": {"eligible": 0, "requested": 0, "measured": 0, "errors": 0},
                "currencies": [],
                "spend_aggregated": True,
                "totals": {},
                "observations": [],
            },
            "crm": {},
            "coverage": {"social": {"measured": 1}, "paid_media": {"measured": 0}},
        })

    def test_empty_company_distinguishes_ready_surfaces_from_missing_scenario_data(self):
        payload = self.runtime.product_uat_readiness(self.company["id"])
        by_code = {row["code"]: row for row in payload["journey"]}
        self.assertEqual(payload["schema"], "binario.marketing.product-uat-readiness.v1")
        self.assertEqual(by_code["COMPANY_CONTEXT"]["status"], "READY")
        self.assertEqual(by_code["DAILY_DESK"]["status"], "READY")
        self.assertEqual(by_code["COMMERCIAL_FLOW"]["status"], "NEEDS_DATA")
        self.assertEqual(by_code["CAMPAIGN_PLANNING"]["status"], "NEEDS_DATA")
        self.assertEqual(by_code["EXECUTION_HANDOFF"]["status"], "WAITING")
        self.assertEqual(by_code["RESULTS_LEARNING"]["status"], "WAITING")
        self.assertEqual(by_code["AI_INTERPRETATION"]["status"], "OPTIONAL")
        self.assertTrue(payload["summary"]["ready_for_manual_uat"])
        self.assertFalse(payload["summary"]["production_ready"])
        self.assertFalse(payload["summary"]["physical_uat_recorded"])

    def test_controlled_crm_campaign_and_snapshot_advance_readiness_without_remote_work(self):
        contact = self.runtime.create_contact(self.company["id"], {"name": "Cliente UAT"})
        self.runtime.create_opportunity(self.company["id"], {
            "contact_id": contact["id"],
            "title": "Oportunidad UAT",
            "stage": "NEW",
            "value": 1000000,
            "currency": "COP",
        })
        campaign = self._campaign()
        self._snapshot(campaign)
        with patch.object(self.runtime, "social_analytics_meta", side_effect=AssertionError("provider read forbidden")), \
             patch.object(self.runtime, "company_paid_media_observability", side_effect=AssertionError("provider read forbidden")), \
             patch.object(self.runtime, "social_inbox", side_effect=AssertionError("inbox remote read forbidden")):
            payload = self.runtime.product_uat_readiness(self.company["id"])
        by_code = {row["code"]: row for row in payload["journey"]}
        self.assertEqual(by_code["COMMERCIAL_FLOW"]["status"], "READY")
        self.assertEqual(by_code["PIPELINE"]["status"], "READY")
        self.assertEqual(by_code["CAMPAIGN_PLANNING"]["status"], "READY")
        self.assertEqual(by_code["EXECUTION_HANDOFF"]["status"], "NEEDS_DATA")
        self.assertEqual(by_code["RESULTS_LEARNING"]["status"], "READY")
        self.assertEqual(payload["evidence"]["pipeline_summary"]["open_opportunities"], 1)
        self.assertEqual(payload["evidence"]["execution_summary"]["active_campaigns"], 1)
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["provider_mutation_performed"])
        self.assertFalse(payload["safety"]["background_polling"])
        self.assertFalse(payload["safety"]["cloud_required"])

    def test_company_scope_fails_closed_and_does_not_mix_counts(self):
        self._campaign("Greenatics UAT")
        other = self.runtime.create_company({"name": "Otra"})
        self.runtime.create_campaign(other["id"], {
            "name": "Otra UAT",
            "objective": "SALES",
            "status": "IN_PROGRESS",
            "channels": ["instagram"],
        })
        first = self.runtime.product_uat_readiness(self.company["id"])
        second = self.runtime.product_uat_readiness(other["id"])
        self.assertEqual(first["company"]["id"], self.company["id"])
        self.assertEqual(second["company"]["id"], other["id"])
        self.assertEqual(first["evidence"]["execution_summary"]["active_campaigns"], 1)
        self.assertEqual(second["evidence"]["execution_summary"]["active_campaigns"], 1)
        with self.assertRaises(ValueError):
            self.runtime.product_uat_readiness("company-does-not-exist")

    def test_release_and_workflow_contracts_remain_fail_closed(self):
        payload = self.runtime.product_uat_readiness(self.company["id"])
        self.assertEqual(payload["contracts"]["workflow_count"], 3)
        self.assertEqual(payload["contracts"]["workflows"], ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        self.assertTrue(payload["contracts"]["canonical_workflows_only"])
        self.assertTrue(payload["contracts"]["loopback_default"])
        self.assertFalse(payload["contracts"]["cloud_required"])
        self.assertEqual(payload["release_boundary"]["version"], "0.9.0.dev1")
        self.assertFalse(payload["release_boundary"]["release_ready"])
        self.assertIsNone(payload["release_boundary"]["release_tag"])
        self.assertTrue(payload["release_boundary"]["physical_uat_required"])
        self.assertFalse(payload["release_boundary"]["physical_uat_recorded"])
        self.assertFalse(payload["release_boundary"]["distribution_signing_certified"])
        self.assertFalse(payload["release_boundary"]["notarization_certified"])

    def test_manual_scenarios_keep_mutations_explicit_and_ai_optional(self):
        payload = self.runtime.product_uat_readiness(self.company["id"])
        scenarios = {row["id"]: row for row in payload["manual_scenarios"]}
        self.assertEqual(scenarios["inbox-to-crm"]["status"], "NEEDS_DATA")
        self.assertIn("No hay fuzzy matching", scenarios["inbox-to-crm"]["expected"])
        self.assertIn("Guardar", scenarios["pipeline-followup"]["expected"])
        self.assertIn("no publica ni activa anuncios", scenarios["campaign-execution"]["expected"])
        self.assertIn("LAST_CAPTURED_TOUCH", scenarios["results-decision"]["expected"])
        self.assertEqual(scenarios["optional-ai"]["status"], "OPTIONAL")
        self.assertIn("nunca ejecuta", scenarios["optional-ai"]["expected"])

    def test_http_serves_uat_projection_and_wave66_bootstrap(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/results-intelligence.js", timeout=5) as response:
                intelligence_ui = response.read().decode("utf-8")
            self.assertIn("uat-readiness.js", intelligence_ui)
            self.assertIn("data-uat-readiness-wave66", intelligence_ui)
            with urlopen(base + "/uat-readiness.js", timeout=5) as response:
                uat_ui = response.read().decode("utf-8")
            self.assertIn("UAT & Calidad del producto", uat_ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/uat-readiness", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.product-uat-readiness.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_rehomes_late_waves_and_adds_continuity_without_execution(self):
        ui = (ROOT / "web" / "uat-readiness.js").read_text(encoding="utf-8")
        for marker in (
            "TRABAJO DIARIO",
            "CREAR Y DISTRIBUIR",
            "MEDIR Y MEJORAR",
            "UAT & Calidad",
            "Ejecución",
            "Resultados & IA",
            "Atender / convertir",
            "no certifica por sí sola el Mac físico ni producción",
            "/uat-readiness",
        ):
            self.assertIn(marker, ui)
        self.assertIn("['campaigns','content','video','execution','calendar','publish','pauta']", ui)
        self.assertIn("['analytics','intelligence','learning','ai-copilot','ai']", ui)
        for forbidden in (
            "method:'POST'",
            "method:'PATCH'",
            "method:'PUT'",
            "method:'DELETE'",
            "setInterval",
            "sendBeacon",
            "fetch('https://",
            "supabase",
            "vercel",
        ):
            self.assertNotIn(forbidden, ui)
        self.assertIn("queueMicrotask", ui)
        self.assertNotIn("physical_uat_recorded:true", ui.replace(" ", ""))

    def test_builder_service_audit_and_historical_markers_are_preserved(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave66_app.py").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_wave66_product_uat_readiness.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave65_app','service_wave66_app", builder)
        for audit_name in (
            "audit_wave59_local_product_integration.sh",
            "audit_wave60_daily_workdesk.sh",
            "audit_wave61_commercial_desk.sh",
            "audit_wave62_contact_360.sh",
            "audit_wave63_commercial_pipeline.sh",
            "audit_wave64_execution_workspace.sh",
            "audit_wave65_results_intelligence.sh",
            "audit_wave66_product_uat_readiness.sh",
        ):
            self.assertIn(audit_name, builder)
        for wave in (59, 60, 61, 62, 63, 64, 65, 66):
            self.assertIn(f"CURRENT ARM64 ITERATION BUILD PASS: Wave {wave}", builder)
        self.assertIn("service_wave65_app as base", service)
        self.assertIn("uat.src='/uat-readiness.js'", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertIn('host: str = "127.0.0.1"', service)
        self.assertIn("workflow_names = sorted(_CANONICAL_WORKFLOWS)", service)
        self.assertIn("WAVE 66 PRODUCT UAT READINESS AUDIT PASS", audit)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)


if __name__ == "__main__":
    unittest.main()
