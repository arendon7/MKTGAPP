import tempfile
import unittest
from pathlib import Path

from binario_marketing.service_wave47_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave47ProductSurfaceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_company_workspace_is_single_and_persistent(self):
        before = self.runtime.company_workspace_summary(self.company["id"])
        self.assertIsNone(before["project_id"])
        first = self.runtime.ensure_company_workspace(self.company["id"])
        second = self.runtime.ensure_company_workspace(self.company["id"])
        self.assertEqual(first["project_id"], second["project_id"])
        projects = self.runtime.projects.list_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0].id, first["project_id"])
        self.assertIn("Greenatics", projects[0].name)

    def test_company_paid_media_overrides_browser_meta_identity(self):
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "page_authoritative",
            "facebook_page_name": "Greenatics",
            "instagram_id": "ig_authoritative",
            "instagram_username": "greenatics",
            "ad_account_id": "act_authoritative",
            "ad_account_name": "Greenatics Ads",
        })
        payload = {
            "ad_account_id": "act_attacker",
            "page_id": "page_attacker",
            "instagram_actor_id": "ig_attacker",
            "campaign_name": "Leads agosto",
            "campaign_objective": "OUTCOME_LEADS",
            "special_ad_categories": [],
            "adset_name": "Colombia 21-55",
            "daily_budget": 10000,
            "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}, "age_min": 21, "age_max": 55},
            "creative_name": "Creative A",
            "message": "Conoce nuestra propuesta",
            "link_url": "https://example.com",
            "picture_url": "https://example.com/creative.jpg",
            "call_to_action": "LEARN_MORE",
            "ad_name": "Ad A",
        }
        row = self.runtime.create_company_paid_media(self.company["id"], payload)
        self.assertEqual(row["ad_account_id"], "act_authoritative")
        self.assertEqual(row["page_id"], "page_authoritative")
        self.assertEqual(row["instagram_actor_id"], "ig_authoritative")
        workspace = self.runtime.company_workspace_summary(self.company["id"])
        self.assertEqual(workspace["paid_media"], 1)
        self.assertEqual(self.runtime.company_paid_media(self.company["id"])[0]["id"], row["id"])

    def test_company_paid_media_requires_associated_meta_assets(self):
        payload = {
            "campaign_name": "Leads",
            "campaign_objective": "OUTCOME_LEADS",
            "adset_name": "CO",
            "daily_budget": 10000,
            "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}},
            "creative_name": "A",
            "message": "Mensaje",
            "link_url": "https://example.com",
            "picture_url": "https://example.com/a.jpg",
            "ad_name": "A",
        }
        with self.assertRaisesRegex(ValueError, "ad account"):
            self.runtime.create_company_paid_media(self.company["id"], payload)

    def test_paid_media_draft_is_not_accessible_from_another_company(self):
        self.runtime.companies.update(self.company["id"], {"facebook_page_id": "page_a", "ad_account_id": "act_a"})
        other = self.runtime.create_company({"name": "Otra"})
        self.runtime.companies.update(other["id"], {"facebook_page_id": "page_b", "ad_account_id": "act_b"})
        row = self.runtime.create_company_paid_media(self.company["id"], {
            "campaign_name": "A", "campaign_objective": "OUTCOME_TRAFFIC", "adset_name": "A",
            "daily_budget": 10000, "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}}, "creative_name": "A",
            "message": "Mensaje", "link_url": "https://example.com", "picture_url": "https://example.com/a.jpg",
            "call_to_action": "LEARN_MORE", "ad_name": "A",
        })
        self.runtime.ensure_company_workspace(other["id"])
        with self.assertRaises(KeyError):
            self.runtime._company_paid_media_draft(other["id"], row["id"])

    def test_product_shell_promotes_company_meta_video_and_paid_media(self):
        ui = (ROOT / "web" / "product-shell.js").read_text(encoding="utf-8")
        for text in ("Empresa activa", "Empresas & Meta", "Conectar Meta", "Video Studio", "Pauta", "Crear en Meta · PAUSED", "No se activará gasto"):
            self.assertIn(text, ui)
        self.assertIn("/api/meta/connection", ui)
        self.assertIn("/workspace", ui)
        self.assertIn("/paid-media", ui)
        self.assertNotIn("setInterval(", ui)


if __name__ == "__main__":
    unittest.main()
