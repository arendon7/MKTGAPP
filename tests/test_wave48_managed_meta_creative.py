import base64
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.service_wave48_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z5mEAAAAASUVORK5CYII=")


class Wave48ManagedCreativeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "112233445566", "instagram_id": "998877665544",
            "ad_account_id": "act_123456789012",
        })
        self.media = self.runtime.company_media.add_uploaded(
            self.company["id"], "creative.png", "image", io.BytesIO(PNG), len(PNG)
        )

    def tearDown(self):
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_remote_hierarchy_uses_managed_image_hash_and_paused_status(self):
        now = datetime.now(timezone.utc)
        draft = self.runtime.create_company_paid_media(self.company["id"], {
            "source_kind": "company_media", "company_media_id": self.media.id,
            "start_at": (now + timedelta(days=1)).isoformat(), "end_at": (now + timedelta(days=3)).isoformat(),
            "campaign_name": "Campaign", "campaign_objective": "OUTCOME_TRAFFIC", "special_ad_categories": [],
            "adset_name": "Ad Set", "daily_budget": 3000, "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}, "age_min": 21, "age_max": 55},
            "creative_name": "Creative", "message": "Mensaje", "link_url": "https://example.com",
            "call_to_action": "LEARN_MORE", "ad_name": "Ad",
        })
        calls = []
        def transport(method, url, params):
            endpoint = url.split("/v25.0/", 1)[-1]; calls.append((method, endpoint, dict(params)))
            if endpoint.endswith("/campaigns"): return {"id": "remote_campaign"}
            if endpoint.endswith("/adsets"): return {"id": "remote_adset"}
            if endpoint.endswith("/adimages"): return {"images": {"creative.png": {"hash": "image_hash_123"}}}
            if endpoint.endswith("/adcreatives"): return {"id": "remote_creative"}
            if endpoint.endswith("/ads"): return {"id": "remote_ad"}
            raise AssertionError(endpoint)
        client = MetaGraphClient("local-test-credential", "v25.0", transport=transport)
        with patch("binario_marketing.service_wave48_app.MetaGraphClient.from_env", return_value=client):
            result = self.runtime.create_company_paid_media_remote_paused(self.company["id"], draft["id"])
        self.assertEqual(result["status"], "REMOTE_PAUSED")
        self.assertEqual(result["plan"]["image_hash"], "image_hash_123")
        creative = next(params for _m, endpoint, params in calls if endpoint.endswith("/adcreatives"))
        story = json.loads(creative["object_story_spec"])
        self.assertEqual(story["link_data"]["image_hash"], "image_hash_123")
        self.assertNotIn("picture", story["link_data"])
        for suffix in ("/campaigns", "/adsets", "/ads"):
            params = next(params for _m, endpoint, params in calls if endpoint.endswith(suffix))
            self.assertEqual(params["status"], "PAUSED")
        adset = next(params for _m, endpoint, params in calls if endpoint.endswith("/adsets"))
        self.assertTrue(adset.get("start_time")); self.assertTrue(adset.get("end_time"))
        self.assertTrue(any(endpoint.endswith("/adimages") for _m, endpoint, _p in calls))


if __name__ == "__main__": unittest.main()
