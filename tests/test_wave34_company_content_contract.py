import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.company_media_store import CompanyMediaStore
from binario_marketing.wave27_instagram_local import Wave27MetaSocialPublisher
from binario_marketing.wave34_company_media import Wave34MetaSocialPublisher, Wave34SocialStore


ROOT = Path(__file__).resolve().parents[1]
COMPANY = "company_" + "c" * 24


class FakeMetaClient:
    def __init__(self):
        self.facebook_paths = []

    def publish_page_reel_local(self, target_id, path, message):
        self.facebook_paths.append((target_id, Path(path), message))
        return "fb-remote-1"


class Wave34PublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.media = CompanyMediaStore(root / "records", root / "files")
        self.social = Wave34SocialStore(root / "social")
        body = b"certified-company-reel"
        self.asset = self.media.add_uploaded(COMPANY, "reel.mp4", "video", io.BytesIO(body), len(body))
        self.media.update_probe(COMPANY, self.asset.id, width=1080, height=1920, duration=9.0)

    def tearDown(self):
        self.tmp.cleanup()

    def create_row(self, channel):
        return self.social.create(COMPANY, {
            "channel": channel,
            "target_id": "target-1",
            "target_name": "Target",
            "kind": "reel",
            "message": "Local Reel",
            "asset_id": self.asset.id,
            "scheduled_for": "2030-01-02T12:00:00+00:00",
        })

    def test_facebook_local_reel_uses_managed_company_file(self):
        row = self.create_row("facebook_page")
        client = FakeMetaClient()
        result = Wave34MetaSocialPublisher(self.social, client, media_store=self.media).publish(row.id)
        self.assertEqual(result.status, "PUBLISHED")
        self.assertEqual(result.remote_id, "fb-remote-1")
        self.assertEqual(result.asset_id, self.asset.id)
        self.assertIsNone(result.render_id)
        self.assertEqual(len(client.facebook_paths), 1)
        target, path, message = client.facebook_paths[0]
        self.assertEqual(target, "target-1")
        self.assertEqual(message, "Local Reel")
        self.assertEqual(path, self.media.path_for(COMPANY, self.asset.id))

    def test_instagram_local_reel_enters_wave27_resumable_path_without_persisting_fake_render(self):
        row = self.create_row("instagram")
        publisher = Wave34MetaSocialPublisher(self.social, object(), media_store=self.media)
        with patch.object(Wave27MetaSocialPublisher, "_instagram", autospec=True, return_value="ig-remote-1") as parent:
            remote = publisher._instagram(row)
        self.assertEqual(remote, "ig-remote-1")
        forwarded = parent.call_args.args[1]
        self.assertEqual(forwarded.asset_id, self.asset.id)
        self.assertEqual(forwarded.render_id, self.asset.id)
        self.assertIsNone(self.social.get(row.id).render_id)

    def test_wrong_aspect_is_rejected_before_provider_side_effect(self):
        self.media.update_probe(COMPANY, self.asset.id, width=1920, height=1080, duration=9.0)
        row = self.create_row("facebook_page")
        client = FakeMetaClient()
        result = Wave34MetaSocialPublisher(self.social, client, media_store=self.media).publish(row.id)
        self.assertEqual(result.status, "FAILED")
        self.assertIn("9:16", result.error)
        self.assertEqual(client.facebook_paths, [])


class Wave34UiBuildContractTests(unittest.TestCase):
    def test_content_library_is_company_scoped_and_video_studio_remains_explicit(self):
        js = (ROOT / "web" / "company-content.js").read_text(encoding="utf-8")
        loader = (ROOT / "web" / "instagram-local-reel.js").read_text(encoding="utf-8")
        for required in (
            "Biblioteca de la empresa",
            "Abrir Video Studio",
            "/api/companies/${encodeURIComponent(company.id)}/media",
            "asset_id:localReel?libraryId:null",
            "Biblioteca local",
            "Usar como Reel",
        ):
            self.assertIn(required, js)
        self.assertIn("script.src='/company-content.js'", loader)
        self.assertNotIn("/api/projects',{method:'POST'", js)
        self.assertNotIn("setInterval(()=>submitOpsPublication", js)
        self.assertNotIn("MutationObserver(()=>submitOpsPublication", js)

    def test_local_images_are_managed_but_not_claimed_as_direct_provider_uploads(self):
        js = (ROOT / "web" / "company-content.js").read_text(encoding="utf-8")
        self.assertIn("Disponible en biblioteca", js)
        self.assertIn("kind==='image'", js)
        self.assertNotIn("localImage", js)
        self.assertNotIn("publish_page_photo_local", js)

    def test_full_mac_preserves_wave34_through_certified_extension(self):
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertTrue(
            "from binario_marketing.service_wave34 import serve" in build
            or "from binario_marketing.service_wave35 import serve" in build
            or "from binario_marketing.service_wave36 import serve" in build
            or "from binario_marketing.service_wave37_app import serve" in build
            or "from binario_marketing.service_wave38_app import serve" in build
        )
        self.assertTrue(
            "from binario_marketing.service_wave34 import AppRuntime" in audit
            or "from binario_marketing.service_wave35 import AppRuntime" in audit
            or "from binario_marketing.service_wave36 import AppRuntime" in audit
            or "from binario_marketing.service_wave37_app import AppRuntime" in audit
            or "from binario_marketing.service_wave38_app import AppRuntime" in audit
        )
        self.assertIn("company-content.js", audit)
        self.assertIn("company_media_store.py", audit)
        self.assertIn("wave34_company_media.py", audit)
        self.assertNotIn("service_wave33", build)
        self.assertNotIn("background-scheduling", audit)


if __name__ == "__main__":
    unittest.main()