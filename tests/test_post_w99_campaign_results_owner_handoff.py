import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from binario_marketing.service_post_w99_campaign_results_owner_handoff_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class PostW99CampaignResultsOwnerHandoffTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def _fixture(self, runtime, *, company_name="Results Owner"):
        company = runtime.create_company({"name": company_name})
        company_id = company["id"]
        campaign = runtime.campaigns.create(company_id, {
            "name": "Campaña exacta",
            "objective": "LEADS",
            "status": "IN_PROGRESS",
            "channels": ["instagram"],
        })
        return company_id, campaign

    def test_local_context_validates_exact_campaign_without_provider_or_business_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, campaign = self._fixture(runtime)
                context = runtime.campaign_results_owner_context(company_id, campaign.id)
                self.assertEqual(context["schema"], "binario.marketing.campaign-results-owner-context.v1")
                self.assertEqual(context["company"]["id"], company_id)
                self.assertEqual(context["campaign"]["id"], campaign.id)
                self.assertEqual(context["campaign"]["name"], campaign.name)
                self.assertFalse(context["learning"]["campaign_available"])
                self.assertIsNone(context["learning"]["latest_snapshot"])
                self.assertTrue(context["controls"]["capture_results"]["available"])
                self.assertFalse(context["controls"]["capture_results"]["automatic_provider_read"])
                self.assertFalse(context["controls"]["record_decision"]["available"])
                self.assertTrue(context["contracts"]["campaign_identity_is_exact"])
                self.assertTrue(context["contracts"]["owner_context_is_local_read_only"])
                self.assertTrue(context["contracts"]["learning_refresh_authority_remains_wave52"])
                self.assertTrue(context["contracts"]["decision_authority_remains_wave52"])
                self.assertTrue(context["contracts"]["optional_ai_authority_remains_wave65"])
                self.assertEqual(
                    context["safety"],
                    {
                        "provider_read_performed": False,
                        "provider_mutation_performed": False,
                        "business_mutation_performed": False,
                        "ai_generation_performed": False,
                        "automatic_execution": False,
                        "background_polling": False,
                        "cloud_required": False,
                    },
                )
            finally:
                self._shutdown_runtime(runtime)

    def test_context_rejects_campaign_from_another_company(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                first_id, campaign = self._fixture(runtime, company_name="First")
                second = runtime.create_company({"name": "Second"})
                self.assertNotEqual(first_id, second["id"])
                with self.assertRaises(KeyError):
                    runtime.campaign_results_owner_context(second["id"], campaign.id)
            finally:
                self._shutdown_runtime(runtime)

    def test_context_is_projection_only_and_does_not_replace_wave52_or_wave65_authorities(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_results_owner_handoff_app.py").read_text(encoding="utf-8")
        wave52 = (ROOT / "src" / "binario_marketing" / "service_wave52_app.py").read_text(encoding="utf-8")
        wave65 = (ROOT / "web" / "results-intelligence.js").read_text(encoding="utf-8")
        self.assertIn("def campaign_results_owner_context", service)
        self.assertIn("get_for_company", service)
        self.assertIn("learning_payload", service)
        self.assertIn("results_intelligence_workspace", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_PUT", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertIn("def refresh_learning", wave52)
        self.assertIn("record_learning_decision", wave52)
        self.assertIn("Analizar con IA", wave65)
        self.assertIn("wave65Analyze", wave65)

    def test_http_context_is_get_only_and_static_adapter_bootstraps_after_previous_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company_id, campaign = self._fixture(runtime, company_name="HTTP Results")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                payload = json.loads(urlopen(root + f"/api/companies/{company_id}/campaigns/{campaign.id}/results-owner-context", timeout=5).read().decode("utf-8"))
                self.assertEqual(payload["campaign"]["id"], campaign.id)
                previous = urlopen(root + "/activity-reschedule-control.js", timeout=5).read().decode("utf-8")
                current = urlopen(root + "/campaign-results-owner-handoff.js", timeout=5).read().decode("utf-8")
                self.assertIn("/campaign-results-owner-handoff.js", previous)
                self.assertIn("CAMPAIGN_RESULTS", current)
                self.assertIn("results-owner-context", current)
                with self.assertRaises(HTTPError) as raised:
                    urlopen(root + f"/api/companies/{company_id}/campaigns/not-a-campaign/results-owner-context", timeout=5)
                self.assertIn(raised.exception.code, {400, 404})
            finally:
                server.shutdown();thread.join(timeout=5);server.server_close();self._shutdown_runtime(runtime)

    def test_browser_adapter_maps_results_actions_to_exact_campaign_target(self):
        source = (ROOT / "web" / "campaign-results-owner-handoff.js").read_text(encoding="utf-8")
        for required in (
            "CAMPAIGN_RESULTS",
            "capture_results",
            "review_coverage",
            "record_decision",
            "review_results",
            "data-deep-results-campaign-id",
            "results-owner-context",
            "Actualizar resultados desde Meta",
            "Preparar decisión para esta campaña",
            "W52_SUBMIT_CAMPAIGN_DECISION",
            "REVIEW_EXACT_CAMPAIGN_COVERAGE",
            "REVIEW_EXACT_CAMPAIGN_RESULTS",
        ):
            self.assertIn(required, source)
        self.assertIn("context.target_id=context.campaign_id", source)
        self.assertIn("matches.length===1", source)
        self.assertIn("campaignResultsOwnerPayloadMatches", source)

    def test_decision_preparation_is_human_triggered_ui_state_only(self):
        source = (ROOT / "web" / "campaign-results-owner-handoff.js").read_text(encoding="utf-8")
        self.assertIn("prepare.addEventListener('click'", source)
        self.assertIn("kind.value='CAMPAIGN'", source)
        self.assertIn("entity.value=String(campaignId)", source)
        self.assertIn("form.dataset.postW99PreparedCampaignId", source)
        self.assertIn("Registrar decisión local", (ROOT / "web" / "learning-loop.js").read_text(encoding="utf-8"))
        for forbidden in (
            ".click(",
            "dispatchEvent(",
            "setInterval(",
            "sendBeacon(",
            "method:'POST'",
            "method:'PATCH'",
            "method:'PUT'",
            "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, source)

    def test_optional_ai_handoff_uses_existing_w65_analysis_control_not_generic_ir(self):
        source = (ROOT / "web" / "campaign-results-owner-handoff.js").read_text(encoding="utf-8")
        self.assertIn("targetKind==='CAMPAIGN_INTELLIGENCE'&&kind==='optional_ai'", source)
        self.assertIn("W65_OPTIONAL_AI", source)
        self.assertIn("Analizar con IA", source)
        self.assertIn("generation_requires_explicit_confirmation", (ROOT / "src" / "binario_marketing" / "service_wave65_app.py").read_text(encoding="utf-8"))
        self.assertIn("confirm(`Se enviará contexto marketing sanitizado", (ROOT / "web" / "results-intelligence.js").read_text(encoding="utf-8"))

    def test_action_center_preserves_campaign_id_for_results_owner_resolution(self):
        action_center = (ROOT / "src" / "binario_marketing" / "service_post_w99_action_center_app.py").read_text(encoding="utf-8")
        self.assertIn('"CAPTURE_RESULTS"', action_center)
        self.assertIn('"REVIEW_COVERAGE"', action_center)
        self.assertIn('"RECORD_DECISION"', action_center)
        self.assertIn('"REVIEW_RESULTS"', action_center)
        self.assertIn("campaign_id=campaign.get(\"id\")", action_center)

    def test_docs_preserve_composition_and_frozen_w99_boundary(self):
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_RESULTS_OWNER_HANDOFF.md").read_text(encoding="utf-8")
        entry = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("Wave 52", doc)
        self.assertIn("Wave 65", doc)
        self.assertIn("GET /api/companies/{company_id}/campaigns/{campaign_id}/results-owner-context", doc)
        self.assertIn("W64 second-hop execution relay", doc)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No debe interpretarse como W100", entry)
        expected = "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff"
        self.assertIn(expected, entry)


if __name__ == "__main__":
    unittest.main()
