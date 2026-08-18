import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave47_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave47ProductSurfaceHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
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

    def test_product_shell_bundle_is_served(self):
        with urlopen(self.base + "/product-shell.js", timeout=5) as response:
            text = response.read().decode("utf-8")
        self.assertIn("renderWave47Pauta", text)
        self.assertIn("renderWave47Video", text)
        self.assertIn("Conectar Meta", text)

    def test_company_workspace_endpoint_is_explicit_and_idempotent(self):
        status, before = self.request_json(f"/api/companies/{self.company['id']}/workspace")
        self.assertEqual(status, 200)
        self.assertIsNone(before["project_id"])
        status, first = self.request_json(f"/api/companies/{self.company['id']}/workspace", method="POST", body={})
        self.assertEqual(status, 201)
        self.assertTrue(first["project_id"])
        _, second = self.request_json(f"/api/companies/{self.company['id']}/workspace", method="POST", body={})
        self.assertEqual(first["project_id"], second["project_id"])

    def test_paid_media_api_is_company_scoped(self):
        self.runtime.companies.update(self.company["id"], {"facebook_page_id": "111111111111", "ad_account_id": "222222222222"})
        payload = {
            "campaign_name": "Traffic", "campaign_objective": "OUTCOME_TRAFFIC", "special_ad_categories": [],
            "adset_name": "CO", "daily_budget": 10000, "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}}, "creative_name": "Creative",
            "message": "Mensaje", "link_url": "https://example.com", "picture_url": "https://example.com/a.jpg",
            "call_to_action": "LEARN_MORE", "ad_name": "Ad",
        }
        status, row = self.request_json(f"/api/companies/{self.company['id']}/paid-media", method="POST", body=payload)
        self.assertEqual(status, 201)
        self.assertEqual(row["ad_account_id"], "222222222222")
        _, rows = self.request_json(f"/api/companies/{self.company['id']}/paid-media")
        self.assertEqual([item["id"] for item in rows], [row["id"]])

    def test_loader_places_product_shell_after_wave45(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("reschedule.src='/followup-reschedule.js'", loader)
        self.assertIn("shell.src='/product-shell.js'", loader)
        self.assertIn("reschedule.addEventListener('load',loadProductShell", loader)

    def test_arm64_iteration_wrapper_rejects_intel_and_launches_wave47(self):
        build = (ROOT / "scripts" / "build_full_mac_wave47.sh").read_text(encoding="utf-8")
        self.assertIn('[[ "$ARCH" == "arm64" ]]', build)
        self.assertIn("service_wave47_app import serve", build)
        self.assertIn("audit_wave47_product_surface.sh", build)


if __name__ == "__main__":
    unittest.main()
