import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from binario_marketing.render_queue import RenderRecord
from binario_marketing.service_wave49_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave49CreativeRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "111111111111",
            "facebook_page_name": "Greenatics",
            "instagram_id": "222222222222",
            "instagram_username": "greenatics",
            "ad_account_id": "333333333333",
            "ad_account_name": "Greenatics Ads",
        })

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _image(self):
        payload = b"\x89PNG\r\n\x1a\nwave49"
        return self.runtime.upload_company_media(
            self.company["id"], "creative.png", "image", io.BytesIO(payload), len(payload)
        )

    def _campaign(self, media_ids=None):
        return self.runtime.create_campaign(self.company["id"], {
            "name": "Lanzamiento",
            "objective": "LEADS",
            "status": "PLANNING",
            "channels": ["facebook_page", "instagram"],
            "media_ids": media_ids or [],
        })

    def test_creative_links_campaign_and_scheduled_publication(self):
        media = self._image()
        campaign = self._campaign()
        saved = self.runtime.upsert_company_creative(self.company["id"], media["id"], {
            "title": "Lead creative",
            "stage": "READY",
            "purpose": "LEADS",
            "campaign_id": campaign["id"],
            "channels": ["facebook_page", "paid_media"],
            "primary_copy": "Conoce nuestra propuesta",
            "public_media_url": "https://cdn.example.com/creative.png",
            "publish_at": "2026-08-20T15:00:00-05:00",
        })
        self.assertEqual(saved["campaign"]["id"], campaign["id"])
        campaign_after = self.runtime.campaigns.get_for_company(self.company["id"], campaign["id"])
        self.assertIn(media["id"], campaign_after.media_ids)

        prepared = self.runtime.prepare_creative_publication(
            self.company["id"], media["id"], {"channel": "facebook_page"}
        )
        publication = prepared["publication"]
        self.assertEqual(publication["status"], "QUEUED")
        self.assertEqual(publication["kind"], "image")
        self.assertEqual(publication["media_url"], "https://cdn.example.com/creative.png")
        profile = self.runtime.creatives.get(self.company["id"], media["id"])
        self.assertEqual(profile.stage, "SCHEDULED")
        self.assertIn(publication["id"], profile.publication_ids)
        campaign_after = self.runtime.campaigns.get_for_company(self.company["id"], campaign["id"])
        self.assertIn(publication["id"], campaign_after.publication_ids)

    def test_paid_media_from_managed_creative_is_auto_linked(self):
        media = self._image()
        campaign = self._campaign()
        self.runtime.upsert_company_creative(self.company["id"], media["id"], {
            "title": "Paid creative",
            "stage": "READY",
            "purpose": "LEADS",
            "campaign_id": campaign["id"],
            "channels": ["paid_media"],
            "primary_copy": "Mensaje desde Creative Studio",
            "destination_url": "https://example.com/landing",
            "call_to_action": "LEARN_MORE",
        })
        row = self.runtime.create_company_paid_media(self.company["id"], {
            "campaign_id": campaign["id"],
            "source_kind": "company_media",
            "company_media_id": media["id"],
            "campaign_name": "Meta Leads",
            "campaign_objective": "OUTCOME_LEADS",
            "special_ad_categories": [],
            "adset_name": "CO Leads",
            "daily_budget": 10000,
            "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}, "age_min": 25, "age_max": 55},
            "creative_name": "Creative A",
            "message": "Mensaje desde Creative Studio",
            "link_url": "https://example.com/landing",
            "call_to_action": "LEARN_MORE",
            "ad_name": "Ad A",
        })
        profile = self.runtime.creatives.get(self.company["id"], media["id"])
        self.assertEqual(profile.stage, "PAID")
        self.assertIn(row["id"], profile.paid_media_ids)
        self.assertEqual(row["creative_source"]["id"], media["id"])

    def test_completed_render_promotion_is_content_addressed(self):
        workspace = self.runtime.ensure_company_workspace(self.company["id"])
        project_id = workspace["project_id"]
        data = b"wave49-render-output"
        digest = hashlib.sha256(data).hexdigest()
        render = RenderRecord(
            id="a1b2c3d4e5f6",
            project_id=project_id,
            asset_id="source",
            output_name="campaign-reel.mp4",
            output_relative_path="exports/campaign-reel.mp4",
            start=0.0,
            end=5.0,
            width=1080,
            height=1920,
            status="PASS",
            progress=1.0,
            created_at="2026-08-18T00:00:00+00:00",
            updated_at="2026-08-18T00:00:01+00:00",
            sha256=digest,
            bytes=len(data),
        )
        output = self.runtime.projects.export_path(project_id, render.output_name)
        output.write_bytes(data)
        self.runtime.renders._replace(render)
        first = self.runtime.promote_company_render(self.company["id"], render.id, {"title": "Reel campaña"})
        second = self.runtime.promote_company_render(self.company["id"], render.id, {"title": "Reel campaña"})
        self.assertEqual(first["media"]["id"], second["media"]["id"])
        self.assertEqual(first["media"]["sha256"], digest)
        self.assertEqual(len(self.runtime.company_media.list(self.company["id"])), 1)
        self.assertEqual(first["creative"]["title"], "Reel campaña")


if __name__ == "__main__":
    unittest.main()
