from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.portfolio_campaigns import PORTFOLIO_CAMPAIGNS_SCHEMA, build_portfolio_campaigns
from binario_marketing.service_post_w99_portfolio_campaigns_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PortfolioCampaignsPureTests(unittest.TestCase):
    def test_projection_reuses_w65_and_omits_cross_company_sensitive_fields(self):
        company = {"id": "company_" + "1" * 24, "name": "Marca Uno"}
        intelligence = {
            company["id"]: {
                "campaigns": [{
                    "campaign": {
                        "id": "campaign-a", "name": "Ventas Q4", "objective": "SALES", "status": "IN_PROGRESS",
                        "channels": ["instagram", "facebook_page"], "start_at": "2026-09-10T10:00:00+00:00", "end_at": None,
                        "audience_contacts": 27, "notes": "private strategy",
                    },
                    "execution": {
                        "requires_action": True,
                        "creative": {"ready": 2, "total": 3, "items": [{"media_id": "media-secret", "name": "Creative"}]},
                        "organic": {"publications": 2, "failed": 1, "counts": {"FAILED": 1}},
                        "paid": {"plans": 1, "remote_paused": 1, "counts": {"REMOTE_PAUSED": 1}},
                    },
                    "evidence": {"level": "OBSERVED", "label": "Señal observada", "has_signal": True, "raw": "private evidence"},
                    "attribution": {"attributed_opportunities": 3, "attributed_won": 1, "contacts": ["contact-secret"]},
                    "decision": {"id": "decision-secret", "notes": "private"},
                    "latest_ai": {"id": "ai-secret", "text": "private model output"},
                    "next_action": {"code": "FIX_EXECUTION", "label": "Revisar ejecución", "view": "execution", "media_id": "media-a", "private": "secret"},
                    "requires_attention": True,
                }],
            }
        }
        paid = {
            company["id"]: [{
                "id": "paid-a", "status": "DRAFT", "campaign_name": "Meta Sales",
                "ad_account_id": "act-secret", "page_id": "page-secret", "instagram_actor_id": "ig-secret",
                "targeting": {"geo_locations": {"countries": ["CO"]}}, "message": "private ad copy",
                "link_url": "https://private.example", "picture_url": "https://private.example/image.jpg",
                "campaign_id": "remote-campaign-secret", "adset_id": "remote-adset-secret", "creative_id": "remote-creative-secret", "ad_id": "remote-ad-secret",
                "plan": {"campaign_id": "campaign-a", "currency": "COP", "start_at": "2026-09-11T00:00:00+00:00", "end_at": None, "notes": "private paid notes", "image_hash": "secret-hash"},
                "marketing_campaign": {"id": "campaign-a", "name": "Ventas Q4", "status": "IN_PROGRESS"},
            }]
        }
        payload = build_portfolio_campaigns([company], intelligence, paid, generated_at="2026-09-10T12:00:00+00:00")
        self.assertEqual(payload["schema"], PORTFOLIO_CAMPAIGNS_SCHEMA)
        self.assertEqual(payload["summary"]["active_campaigns"], 1)
        self.assertEqual(payload["summary"]["requires_attention"], 1)
        self.assertEqual(payload["summary"]["with_results_signal"], 1)
        self.assertEqual(payload["summary"]["attributed_opportunities"], 3)
        self.assertEqual(payload["summary"]["paid_drafts"], 1)
        row = payload["campaigns"][0]
        self.assertEqual(row["execution"]["creative_ready"], 2)
        self.assertEqual(row["next_action"]["code"], "FIX_EXECUTION")
        self.assertTrue(row["human_decision_recorded"])
        self.assertTrue(row["ai_analysis_available"])
        serialized = json.dumps(payload)
        for forbidden in (
            "private strategy", "contact-secret", "decision-secret", "private model output", "media-secret",
            "act-secret", "page-secret", "ig-secret", "private ad copy", "private.example", "remote-campaign-secret",
            "remote-adset-secret", "remote-creative-secret", "remote-ad-secret", "private paid notes", "secret-hash",
            '"targeting"', '"message"', '"link_url"', '"picture_url"', '"ad_account_id"', '"page_id"',
        ):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(payload["contracts"]["w65_is_campaign_intelligence_authority"])
        self.assertTrue(payload["contracts"]["wave48_is_paid_media_mutation_authority"])
        self.assertTrue(payload["contracts"]["no_cross_company_provider_reads"])

    def test_local_errors_fail_closed_without_inventing_campaigns(self):
        company = {"id": "company_" + "2" * 24, "name": "Marca Dos"}
        payload = build_portfolio_campaigns(
            [company],
            {company["id"]: {"_local_state_error": True, "campaigns": []}},
            {company["id"]: {"_local_state_error": True}},
        )
        self.assertEqual(payload["summary"]["local_state_errors"], 1)
        self.assertEqual(payload["campaigns"], [])
        self.assertEqual(payload["paid_media"], [])
        self.assertEqual(payload["companies"][0]["state"], "LOCAL_STATE_ERROR")


class PortfolioCampaignsRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.companies.create("Marca Runtime")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_runtime_and_http_are_local_read_only(self):
        payload = self.runtime.portfolio_campaigns()
        self.assertEqual(payload["schema"], PORTFOLIO_CAMPAIGNS_SCHEMA)
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["provider_mutation_performed"])
        self.assertFalse(payload["safety"]["campaign_mutation_performed"])
        self.assertFalse(payload["safety"]["paid_media_mutation_performed"])
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/api/portfolio/campaigns", timeout=5) as response:
                api_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(api_payload["schema"], PORTFOLIO_CAMPAIGNS_SCHEMA)
            with urlopen(root + "/portfolio-campaigns.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_PORTFOLIO_CAMPAIGNS", source)
            with urlopen(root + "/portfolio-content.js", timeout=5) as response:
                chained = response.read().decode("utf-8")
            self.assertIn("/portfolio-campaigns.js", chained)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_contract_has_no_cross_company_mutation_or_background_loop(self):
        source = (ROOT / "web" / "portfolio-campaigns.js").read_text(encoding="utf-8")
        for required in (
            "/api/portfolio/campaigns", "PORTFOLIO / MULTIEMPRESA", "Campañas", "Pauta",
            "portfolioNavigate", "campaignRenderCurrent", "renderWave47Pauta", "Ver todas las empresas",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "method:'POST'", "method:'PATCH'", "method:'DELETE'", "setInterval(", "setTimeout(",
            "MutationObserver", "localStorage", "sessionStorage", "fetch('https://", 'fetch("https://',
        ):
            self.assertNotIn(forbidden, source)

    def test_dev_alias_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_campaigns_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_content_app as base", service)
        self.assertIn("results_intelligence_workspace", service)
        self.assertIn("company_paid_media", service)
        self.assertIn("/api/portfolio/campaigns", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_campaigns_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PORTFOLIO_CAMPAIGNS.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("w65", docs.casefold())
        self.assertIn("w48", docs.casefold())


if __name__ == "__main__":
    unittest.main()
