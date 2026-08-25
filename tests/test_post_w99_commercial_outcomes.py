import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_commercial_outcomes_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PostW99CommercialOutcomesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.other = self.runtime.create_company({"name": "Otra Empresa"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _campaign(self, name="Campaña comercial", company=None):
        company = company or self.company
        return self.runtime.create_campaign(company["id"], {
            "name": name, "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]
        })

    def _link(self, campaign, source="instagram"):
        return self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": campaign["id"], "destination_url": "https://example.com/landing",
            "utm_source": source, "utm_medium": "paid_social",
        })

    def _captured_lead(self, link, email, name="Lead"):
        return self.runtime.intake_lead(self.company["id"], {
            "connector": "FIRST_PARTY_FORM", "name": name, "email": email,
            "attribution_capture": {"bm_tid": link["tracking_code"], "utm_source": link["utm_source"]},
        })

    def test_tracking_link_is_instrumentation_not_click_or_lead(self):
        campaign = self._campaign(); self._link(campaign)
        payload = self.runtime.commercial_outcomes(self.company["id"])
        row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["funnel"]["tracking_links"], 1)
        self.assertEqual(row["funnel"]["captured_touches"], 0)
        self.assertEqual(row["funnel"]["captured_leads"], 0)
        self.assertEqual(row["commercial_next_action"]["code"], "CHECK_CAPTURE_COVERAGE")
        self.assertFalse(payload["model"]["tracking_link_means_click"])
        self.assertFalse(payload["model"]["temporal_inference"])

    def test_exact_captured_lead_is_visible_before_crm_conversion(self):
        campaign = self._campaign(); link = self._link(campaign); lead = self._captured_lead(link, "lead@example.com")
        payload = self.runtime.commercial_outcomes(self.company["id"])
        row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["funnel"]["captured_leads"], 1)
        self.assertEqual(row["funnel"]["unresolved_captured_leads"], 1)
        self.assertEqual(row["funnel"]["attributed_opportunities"], 0)
        self.assertEqual(row["commercial_next_action"]["code"], "RESOLVE_CAPTURED_LEADS")
        self.assertEqual(row["journeys"][0]["lead_id"], lead["id"])
        self.assertEqual(row["journeys"][0]["evidence"], "EXACT_TRACKING_LINK")

    def test_conversion_without_opportunity_is_not_counted_as_sale(self):
        campaign = self._campaign(); link = self._link(campaign); lead = self._captured_lead(link, "contact@example.com")
        result = self.runtime.convert_lead(self.company["id"], lead["id"], {"action": "CREATE_CONTACT"})
        self.assertIsNotNone(result["converted_contact_id"]); self.assertIsNone(result["converted_opportunity_id"])
        row = next(item for item in self.runtime.commercial_outcomes(self.company["id"])["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["funnel"]["converted_leads"], 1)
        self.assertEqual(row["funnel"]["converted_without_opportunity"], 1)
        self.assertEqual(row["funnel"]["attributed_won"], 0)
        self.assertEqual(row["commercial_next_action"]["code"], "CREATE_OPPORTUNITIES")

    def test_won_values_remain_separate_by_currency(self):
        campaign = self._campaign(); link = self._link(campaign)
        lead_cop = self._captured_lead(link, "cop@example.com", "COP")
        lead_usd = self._captured_lead(link, "usd@example.com", "USD")
        self.runtime.convert_lead(self.company["id"], lead_cop["id"], {"action": "CREATE_CONTACT", "opportunity": {"title": "Venta COP", "stage": "WON", "value": 500000, "currency": "COP"}})
        self.runtime.convert_lead(self.company["id"], lead_usd["id"], {"action": "CREATE_CONTACT", "opportunity": {"title": "Venta USD", "stage": "WON", "value": 300, "currency": "USD"}})
        payload = self.runtime.commercial_outcomes(self.company["id"]); row = next(item for item in payload["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertEqual(row["funnel"]["attributed_opportunities"], 2); self.assertEqual(row["funnel"]["attributed_won"], 2)
        self.assertEqual(row["value_by_currency"]["COP"]["won_value"], 500000)
        self.assertEqual(row["value_by_currency"]["USD"]["won_value"], 300)
        self.assertFalse(payload["model"]["currencies_combined"]); self.assertFalse(payload["model"]["probabilistic_forecast"])

    def test_last_captured_touch_credits_one_opportunity_once(self):
        campaign_a = self._campaign("Primera"); campaign_b = self._campaign("Última")
        link_a = self._link(campaign_a, "instagram"); link_b = self._link(campaign_b, "facebook")
        contact = self.runtime.create_contact(self.company["id"], {"name": "Persona"})
        opportunity = self.runtime.create_opportunity(self.company["id"], {"contact_id": contact["id"], "title": "Venta", "stage": "WON", "value": 200000, "currency": "COP"})
        self.runtime.record_attribution_claim(self.company["id"], {"tracking_code": link_a["tracking_code"], "opportunity_id": opportunity["id"], "captured_at": "2026-08-24T10:00:00+00:00"})
        self.runtime.record_attribution_claim(self.company["id"], {"tracking_code": link_b["tracking_code"], "opportunity_id": opportunity["id"], "captured_at": "2026-08-24T11:00:00+00:00"})
        payload = self.runtime.commercial_outcomes(self.company["id"]); by_id = {row["campaign"]["id"]: row for row in payload["campaigns"]}
        self.assertEqual(by_id[campaign_a["id"]]["funnel"]["attributed_opportunities"], 0)
        self.assertEqual(by_id[campaign_b["id"]]["funnel"]["attributed_opportunities"], 1)
        self.assertEqual(payload["summary"]["attributed_opportunities"], 1)
        self.assertEqual(payload["model"]["crm_credit"], "LAST_CAPTURED_TOUCH")

    def test_results_and_command_center_receive_additive_commercial_truth(self):
        campaign = self._campaign(); link = self._link(campaign); lead = self._captured_lead(link, "open@example.com")
        results = self.runtime.results_intelligence_workspace(self.company["id"])
        result_row = next(item for item in results["campaigns"] if item["campaign"]["id"] == campaign["id"])
        self.assertIn("next_action", result_row); self.assertIn("commercial_outcome", result_row)
        self.assertEqual(result_row["commercial_outcome"]["next_action"]["code"], "RESOLVE_CAPTURED_LEADS")
        self.assertIn("commercial_outcomes", results)
        command = self.runtime.marketing_command_center(self.company["id"])
        self.assertIn("commercial_outcomes", command)
        self.assertEqual(command["commercial_outcomes"]["summary"]["captured_leads"], 1)
        self.assertEqual(command["commercial_outcomes"]["attention"][0]["campaign_id"], campaign["id"])
        self.assertEqual(lead["status"], "NEW")

    def test_company_scope_excludes_foreign_campaigns_and_crm(self):
        self._campaign("Propia")
        foreign_campaign = self._campaign("Ajena", self.other)
        payload = self.runtime.commercial_outcomes(self.company["id"])
        ids = {row["campaign"]["id"] for row in payload["campaigns"]}
        self.assertNotIn(foreign_campaign["id"], ids)
        self.assertEqual(payload["company"]["id"], self.company["id"])
        self.assertTrue(payload["safety"]["company_scoped"]); self.assertTrue(payload["safety"]["read_only_projection"])

    def test_http_bootstrap_and_frontend_are_read_only(self):
        self._campaign(); server = create_server(self.runtime, "127.0.0.1", 0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/navigator.js", timeout=5) as response: bootstrap = response.read().decode("utf-8")
            self.assertIn("commercial-outcomes.js", bootstrap); self.assertIn("data-post-w99-commercial-outcomes", bootstrap)
            with urlopen(base + "/commercial-outcomes.js", timeout=5) as response: ui = response.read().decode("utf-8")
            self.assertIn("Resultados comerciales", ui); self.assertIn("Link de tracking", ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/commercial-outcomes", timeout=5) as response: payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.commercial-outcomes.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
        ui = (ROOT / "web" / "commercial-outcomes.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_commercial_outcomes_app.py").read_text(encoding="utf-8")
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", "setInterval", "sendBeacon", "fetch('https://"):
            self.assertNotIn(forbidden, ui)
        self.assertNotIn("def do_POST", service); self.assertNotIn("def do_PATCH", service); self.assertNotIn("def do_DELETE", service)


if __name__ == "__main__":
    unittest.main()
