import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave48_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave48PaidMediaHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "112233445566", "ad_account_id": "act_123456789012",
        })
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start(); self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def get_json(self, path):
        with urlopen(self.base + path, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_paid_media_center_bundle_is_served(self):
        with urlopen(self.base + "/paid-media-center.js", timeout=5) as response:
            text = response.read().decode("utf-8")
        self.assertIn("PAID MEDIA CENTER", text)
        self.assertIn("renderWave47Pauta", text)
        self.assertIn("Actualizar estado y resultados", text)

    def test_context_endpoint_exposes_campaigns_images_account_and_safety(self):
        campaign = self.runtime.create_campaign(self.company["id"], {"name": "Campaña", "objective": "LEADS"})
        status, data = self.get_json(f"/api/companies/{self.company['id']}/paid-media/context")
        self.assertEqual(status, 200)
        self.assertEqual(data["campaigns"][0]["id"], campaign["id"])
        self.assertEqual(data["ad_account"]["id"], "act_123456789012")
        self.assertFalse(data["safety"]["activation_supported"])
        self.assertEqual(data["safety"]["remote_create_status"], "PAUSED")

    def test_loader_orders_wave48_after_wave47(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("shell.src='/product-shell.js'", loader)
        self.assertIn("paid.src='/paid-media-center.js'", loader)
        self.assertIn("shell.addEventListener('load',loadPaidMediaCenter", loader)


if __name__ == "__main__": unittest.main()
