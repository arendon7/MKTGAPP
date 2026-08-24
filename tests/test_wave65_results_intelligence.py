import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave65_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave65ResultsIntelligenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data"); self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def _campaign(self, name="Campaña W65"):
        return self.runtime.create_campaign(self.company["id"], {"name": name, "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["facebook_page", "instagram"]})

    def _snapshot(self, campaign, *, reach=100, interactions=10, clicks=0):
        paid = []
        if clicks:
            paid.append({"campaign_id": campaign["id"], "creative_media_id": None, "currency": "COP", "metrics": {"impressions": 1000, "reach": 800, "clicks": clicks, "spend": 25000}})
        return self.runtime.learning.create_snapshot(self.company["id"], {
            "date_preset": "last_7d",
            "social": {"coverage": {"eligible": 1, "requested": 1, "measured": 1, "errors": 0}, "totals": {"reach": reach, "total_interactions": interactions}, "observations": [{"campaign_id": campaign["id"], "creative_media_id": None, "metrics": {"reach": reach, "total_interactions": interactions}}]},
            "paid_media": {"coverage": {"eligible": len(paid), "requested": len(paid), "measured": len(paid), "errors": 0}, "currencies": ["COP"] if paid else [], "spend_aggregated": True, "totals": {"clicks": clicks, "spend": 25000} if paid else {}, "observations": paid},
            "crm": {}, "coverage": {"social": {"measured": 1}, "paid_media": {"measured": len(paid)}},
        })

    def test_observed_evidence_requires_human_decision_before_ai(self):
        campaign = self._campaign(); snapshot = self._snapshot(campaign, clicks=20); payload = self.runtime.results_intelligence_workspace(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(payload["schema"], "binario.marketing.results-intelligence.v1"); self.assertEqual(row["evidence"]["level"], "OBSERVED"); self.assertEqual(row["evidence"]["metrics"]["paid_ctr"], 2.0); self.assertEqual(row["next_action"]["code"], "RECORD_DECISION"); self.assertTrue(row["requires_attention"]); self.assertEqual(payload["latest_snapshot"]["id"], snapshot.id); self.assertFalse(payload["safety"]["ai_generation_performed"])

    def test_recorded_decision_keeps_ai_optional_and_non_executing(self):
        campaign = self._campaign(); snapshot = self._snapshot(campaign)
        self.runtime.record_learning_decision(self.company["id"], {"entity_kind": "CAMPAIGN", "entity_id": campaign["id"], "action": "ITERATE", "rationale": "La evidencia observada justifica probar una variante.", "snapshot_id": snapshot.id})
        self.runtime.ai_settings.update(self.company["id"], {"provider": "ollama", "model": "llama3.2"}); payload = self.runtime.results_intelligence_workspace(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["decision"]["action"], "ITERATE"); self.assertEqual(row["next_action"]["code"], "OPTIONAL_AI"); self.assertFalse(row["requires_attention"]); self.assertTrue(payload["ai"]["configured"]); self.assertFalse(payload["ai"]["marketing_execution_authority"]); self.assertTrue(payload["ai"]["generation_requires_explicit_user_action"])

    def test_partial_attribution_is_separate_from_observed_metrics(self):
        campaign = self._campaign(); contact = self.runtime.create_contact(self.company["id"], {"name": "Persona"})
        opportunity = self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "Venta W65", "stage": "WON", "value": 2500000, "currency": "COP"})
        link = self.runtime.create_tracking_link(self.company["id"], {"campaign_id": campaign["id"], "destination_url": "https://example.com/landing", "utm_source": "instagram", "utm_medium": "paid_social"})
        self.runtime.record_attribution_claim(self.company["id"], {"tracking_code": link["tracking_code"], "opportunity_id": opportunity["id"]})
        payload = self.runtime.results_intelligence_workspace(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["evidence"]["level"], "ATTRIBUTED_WON"); self.assertFalse(row["evidence"]["observed"]); self.assertEqual(row["attribution"]["attributed_opportunities"], 1); self.assertEqual(row["attribution"]["attributed_won"], 1); self.assertEqual(row["attribution"]["value_by_currency"]["COP"]["won_value"], 2500000); self.assertEqual(row["attribution"]["model"], "LAST_CAPTURED_TOUCH"); self.assertFalse(payload["attribution_coverage"]["full_funnel_coverage_assumed"])

    def test_latest_ai_is_compact_history_not_source_of_truth(self):
        campaign = self._campaign(); snapshot = self._snapshot(campaign)
        self.runtime.record_learning_decision(self.company["id"], {"entity_kind": "CAMPAIGN", "entity_id": campaign["id"], "action": "HOLD", "rationale": "Esperar más evidencia.", "snapshot_id": snapshot.id})
        self.runtime.ai_settings.update(self.company["id"], {"provider": "ollama", "model": "llama3.2"}); context = {"schema": "test", "privacy": {"contact_pii_included": False}}; digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        session = self.runtime.ai_sessions.create(self.company["id"], provider="ollama", model="llama3.2", task="CAMPAIGN", campaign_id=campaign["id"], creative_media_id=None, instruction="Analiza evidencia", context_sha256=digest, context=context, output={"summary": "Mantener y observar.", "diagnosis": ["La muestra todavía es limitada."], "recommendations": [{"title": "Esperar más señal", "why": "La cobertura aún es corta.", "priority": "MEDIUM", "area": "CAMPAIGN", "next_step": "Capturar otro snapshot."}], "creative_variants": [], "campaign_brief": {}}, provider_meta={})
        payload = self.runtime.results_intelligence_workspace(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["latest_ai"]["id"], session.id); self.assertEqual(row["latest_ai"]["summary"], "Mantener y observar."); self.assertEqual(row["latest_ai"]["recommendation_count"], 1); self.assertNotIn("context", row["latest_ai"]); self.assertEqual(payload["summary"]["with_ai_analysis"], 1); self.assertFalse(payload["safety"]["automatic_recommendation_execution"])

    def test_workspace_is_company_scoped_and_provider_read_free(self):
        first = self._campaign("Greenatics only"); other = self.runtime.create_company({"name": "Otra empresa"}); second = self.runtime.create_campaign(other["id"], {"name": "Otra only", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]})
        with patch.object(self.runtime, "social_analytics_meta", side_effect=AssertionError("provider read forbidden")), patch.object(self.runtime, "company_paid_media_observability", side_effect=AssertionError("provider read forbidden")):
            first_payload = self.runtime.results_intelligence_workspace(self.company["id"]); second_payload = self.runtime.results_intelligence_workspace(other["id"])
        self.assertEqual({row["campaign"]["id"] for row in first_payload["campaigns"]}, {first["id"]}); self.assertEqual({row["campaign"]["id"] for row in second_payload["campaigns"]}, {second["id"]}); self.assertFalse(first_payload["safety"]["provider_read_performed"]); self.assertFalse(first_payload["safety"]["provider_mutation_performed"]); self.assertFalse(first_payload["safety"]["background_polling"]); self.assertFalse(first_payload["safety"]["cloud_required"])

    def test_http_serves_results_workspace_and_wave65_bootstrap(self):
        self._campaign(); server = create_server(self.runtime, "127.0.0.1", 0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/execution-workspace.js", timeout=5) as response: execution_ui = response.read().decode("utf-8")
            self.assertIn("results-intelligence.js", execution_ui); self.assertIn("data-results-intelligence-wave65", execution_ui)
            with urlopen(base + "/results-intelligence.js", timeout=5) as response: intelligence_ui = response.read().decode("utf-8")
            self.assertIn("Resultados, aprendizaje y recomendación", intelligence_ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/results-intelligence", timeout=5) as response: payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.results-intelligence.v1")
        finally: server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_only_generates_ai_explicitly_and_never_executes_marketing(self):
        ui = (ROOT / "web" / "results-intelligence.js").read_text(encoding="utf-8")
        for marker in ("Resultados & IA", "Evidencia determinística primero", "LAST_CAPTURED_TOUCH", "Solo requieren atención", "Analizar con IA", "/ai/generate", "La IA no publicará, activará pauta ni ejecutará decisiones"): self.assertIn(marker, ui)
        self.assertEqual(ui.count("method:'POST'"), 1)
        for forbidden in ("method:'PATCH'", "method:'PUT'", "method:'DELETE'", "setInterval", "sendBeacon", "fetch('https://"): self.assertNotIn(forbidden, ui)
        self.assertIn("confirm(`Se enviará contexto marketing sanitizado", ui); self.assertIn("task:'CAMPAIGN'", ui); self.assertNotIn("/learning/refresh", ui)

    def test_builder_service_workflows_and_release_boundary(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8"); service = (ROOT / "src" / "binario_marketing" / "service_wave65_app.py").read_text(encoding="utf-8")
        self.assertIn("service_wave64_app','service_wave65_app", builder)
        for audit in ("audit_wave59_local_product_integration.sh", "audit_wave60_daily_workdesk.sh", "audit_wave61_commercial_desk.sh", "audit_wave62_contact_360.sh", "audit_wave63_commercial_pipeline.sh", "audit_wave64_execution_workspace.sh", "audit_wave65_results_intelligence.sh"): self.assertIn(audit, builder)
        for wave in (59, 60, 61, 62, 63, 64, 65): self.assertIn(f"CURRENT ARM64 ITERATION BUILD PASS: Wave {wave}", builder)
        self.assertIn("service_wave64_app as base", service); self.assertIn("intelligence.src='/results-intelligence.js'", service); self.assertNotIn("def do_POST", service); self.assertNotIn("def do_PATCH", service); self.assertNotIn("def do_DELETE", service); self.assertIn('host: str = "127.0.0.1"', service)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml")); self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8"); self.assertIn('__version__ = "0.9.0"', version); self.assertIn("RELEASE_READY = True", version); self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        self.assertEqual(source_release_state(), PREPARED_RELEASE); readiness = source_release_readiness(); self.assertTrue(readiness["source_ready"]); self.assertFalse(readiness["operational_inputs_complete"]); self.assertFalse(readiness["production_ready"])


if __name__ == "__main__":
    unittest.main()
