import base64
import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.paid_media_plan_store import PaidMediaPlanStore
from binario_marketing.service_wave48_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z5mEAAAAASUVORK5CYII=")


class Wave48PaidMediaPlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "112233445566",
            "ad_account_id": "act_123456789012",
        })
        self.campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Leads agosto", "objective": "LEADS", "status": "READY",
        })
        self.media = self.runtime.company_media.add_uploaded(
            self.company["id"], "creative.png", "image", io.BytesIO(PNG), len(PNG)
        )

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def payload(self, **extra):
        now = datetime.now(timezone.utc)
        row = {
            "campaign_id": self.campaign["id"], "source_kind": "company_media",
            "company_media_id": self.media.id, "currency": "COP",
            "start_at": (now + timedelta(days=1)).isoformat(),
            "end_at": (now + timedelta(days=8)).isoformat(), "date_preset": "last_7d",
            "campaign_name": "Leads agosto Meta", "campaign_objective": "OUTCOME_LEADS",
            "special_ad_categories": [], "adset_name": "CO 21-55", "daily_budget": 3000,
            "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}, "age_min": 21, "age_max": 55},
            "creative_name": "Creative A", "message": "Conoce nuestra propuesta",
            "link_url": "https://example.com", "call_to_action": "LEARN_MORE", "ad_name": "Ad A",
        }
        row.update(extra); return row

    def test_store_reuses_canonical_ids_and_schedule_contract(self):
        store = PaidMediaPlanStore(Path(self.tmp.name) / "plans")
        row = store.create("a" * 32, self.company["id"], {
            "campaign_id": self.campaign["id"], "source_kind": "company_media",
            "company_media_id": self.media.id, "currency": "cop",
            "start_at": "2026-08-18T09:00:00-05:00", "end_at": "2026-08-20T09:00:00-05:00",
        })
        self.assertEqual(row.currency, "COP")
        self.assertEqual(row.campaign_id, self.campaign["id"])
        with self.assertRaisesRegex(ValueError, "after start_at"):
            store.create("b" * 32, self.company["id"], {
                "source_kind": "public_url", "start_at": "2026-08-20T09:00:00-05:00",
                "end_at": "2026-08-18T09:00:00-05:00",
            })

    def test_plan_links_campaign_and_managed_company_image(self):
        row = self.runtime.create_company_paid_media(self.company["id"], self.payload())
        self.assertEqual(row["plan"]["campaign_id"], self.campaign["id"])
        self.assertEqual(row["creative_source"]["id"], self.media.id)
        self.assertEqual(row["marketing_campaign"]["name"], "Leads agosto")
        self.assertTrue(row["picture_url"].startswith("https://managed.binario.invalid/"))

    def test_campaign_and_media_must_belong_to_same_company(self):
        other = self.runtime.create_company({"name": "Otra"})
        other_campaign = self.runtime.create_campaign(other["id"], {"name": "Otra campaña", "objective": "SALES"})
        with self.assertRaises(KeyError):
            self.runtime.create_company_paid_media(self.company["id"], self.payload(campaign_id=other_campaign["id"]))
        other_media = self.runtime.company_media.add_uploaded(other["id"], "other.png", "image", io.BytesIO(PNG), len(PNG))
        with self.assertRaises(KeyError):
            self.runtime.create_company_paid_media(self.company["id"], self.payload(company_media_id=other_media.id))

    def test_ui_has_deep_center_and_no_activation_route(self):
        ui = (ROOT / "web" / "paid-media-center.js").read_text(encoding="utf-8")
        for text in ("PAID MEDIA CENTER", "Biblioteca de empresa", "Campaña de marketing", "Crear en Meta · PAUSED", "Actualizar estado y resultados", "explicit_active_detected"):
            self.assertIn(text, ui)
        self.assertNotIn("/activate", ui)
        self.assertNotIn("setInterval(", ui)


if __name__ == "__main__": unittest.main()
