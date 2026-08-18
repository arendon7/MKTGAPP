import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave49_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave49CreativeHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        raw = b"\x89PNG\r\n\x1a\nwave49-http"
        self.media = self.runtime.upload_company_media(
            self.company["id"], "creative.png", "image", io.BytesIO(raw), len(raw)
        )
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def request_json(self, path, *, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(self.base + path, method=method, data=data, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_creative_bundle_and_context_are_served(self):
        with urlopen(self.base + "/creative-studio.js", timeout=5) as response:
            text = response.read().decode("utf-8")
        for marker in ("Pipeline creativo", "Enviar a Creative Studio", "Enviar a Pauta", "Preparar Facebook"):
            self.assertIn(marker, text)
        status, context = self.request_json(f"/api/companies/{self.company['id']}/creatives/context")
        self.assertEqual(status, 200)
        self.assertEqual(context["company"]["id"], self.company["id"])
        self.assertEqual(context["items"][0]["media"]["id"], self.media["id"])
        self.assertEqual(context["items"][0]["effective_stage"], "UNPROFILED")

    def test_patch_creative_updates_company_scoped_profile(self):
        status, payload = self.request_json(
            f"/api/companies/{self.company['id']}/creatives/{self.media['id']}",
            method="PATCH",
            body={
                "title": "Creative A",
                "stage": "READY",
                "purpose": "LEADS",
                "channels": ["paid_media"],
                "primary_copy": "Copy A",
                "destination_url": "https://example.com/a",
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["creative"]["title"], "Creative A")
        self.assertEqual(payload["effective_stage"], "READY")

    def test_loader_orders_wave49_after_wave48(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("paid.src='/paid-media-center.js'", loader)
        self.assertIn("paid.addEventListener('load',loadCreativeStudio", loader)
        self.assertIn("creative.src='/creative-studio.js'", loader)

    def test_source_has_no_direct_remote_publish_or_activation_surface(self):
        ui = (ROOT / "web" / "creative-studio.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave49_app.py").read_text(encoding="utf-8")
        self.assertNotIn("publish-now", ui)
        self.assertNotIn("/activate", ui)
        self.assertNotIn("/activate", service)
        self.assertNotIn("setInterval(", ui)
        self.assertIn("prepare_creative_publication", service)
        self.assertIn("create_company_paid_media", service)

    def test_current_arm64_builder_launches_and_audits_wave49(self):
        build = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave49_app", build)
        self.assertIn("audit_wave49_creative_studio.sh", build)
        self.assertIn('[[ "$ARCH" == "arm64" ]]', build)


if __name__ == "__main__":
    unittest.main()
