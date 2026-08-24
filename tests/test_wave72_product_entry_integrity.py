import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave72_app import AppRuntime, REQUIRED_WEB_ASSETS, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave72ProductEntryIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
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

    def _json(self, path: str):
        with urlopen(self.base + path, timeout=10) as response:
            return response.status, json.loads(response.read())

    def _post(self, path: str, payload: dict):
        request = Request(
            self.base + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_root_injects_deterministic_product_entry(self):
        with urlopen(self.base + "/", timeout=10) as response:
            html = response.read().decode("utf-8")
        self.assertEqual(html.count('/product-entry.js'), 1)
        self.assertIn('data-product-entry-wave72="1"', html)
        with urlopen(self.base + "/product-entry.js", timeout=10) as response:
            js = response.read().decode("utf-8")
        self.assertIn("+ Empresa", js)
        self.assertIn("marketing-company-change", js)
        self.assertIn("marketing-ops-refreshed", js)
        self.assertIn("wave72BroadcastContext", js)
        self.assertIn("/api/product-integrity", js)
        self.assertNotIn("setInterval", js)

    def test_every_required_product_asset_is_served(self):
        for name in REQUIRED_WEB_ASSETS:
            with self.subTest(name=name):
                with urlopen(self.base + "/" + name, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                    self.assertGreater(len(response.read()), 0)

    def test_company_create_select_prerequisites_and_all_safe_projections(self):
        status, before = self._json("/api/product-integrity")
        self.assertEqual(status, 200)
        self.assertTrue(before["ready"])
        self.assertEqual(before["inventory"]["present_web_assets"], 46)
        self.assertEqual(before["inventory"]["implemented_runtime_methods"], 33)
        self.assertGreaterEqual(before["inventory"]["registered_apps"], 12)

        status, company = self._post("/api/companies", {"name": "Greenatics UAT"})
        self.assertEqual(status, 201)
        status, companies = self._json("/api/companies")
        self.assertEqual([row["id"] for row in companies], [company["id"]])

        status, integrity = self._json(f"/api/product-integrity?company_id={company['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(integrity["ready"], integrity["missing"])
        self.assertEqual(integrity["company"]["id"], company["id"])
        self.assertEqual(integrity["inventory"]["company_projection_checks"], 27)
        self.assertEqual(integrity["inventory"]["company_projection_pass"], 27)
        self.assertEqual(integrity["missing"], {"web_assets": [], "runtime_methods": [], "failed_company_projections": []})
        self.assertTrue(integrity["safety"]["read_only"])
        self.assertFalse(integrity["safety"]["provider_mutation_performed"])

    def test_release_contract_and_workflow_count_stay_non_authoritative(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src/binario_marketing/service_wave72_app.py").read_text(encoding="utf-8")
        self.assertNotIn("RELEASE_READY = True", service)


if __name__ == "__main__":
    unittest.main()
