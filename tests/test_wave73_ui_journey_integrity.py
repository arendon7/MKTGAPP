import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave72_app import REQUIRED_WEB_ASSETS
from binario_marketing.service_wave73_app import AppRuntime, UI_ASSETS, UI_VIEWS, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave73UiJourneyIntegrityTests(unittest.TestCase):
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
        request = Request(self.base + path, data=json.dumps(payload).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_root_uses_wave73_bootstrap_then_entry(self):
        with urlopen(self.base + "/", timeout=10) as response:
            html = response.read().decode("utf-8")
        self.assertEqual(html.count('/product-bootstrap.js'), 1)
        self.assertEqual(html.count('/product-entry-wave73.js'), 1)
        self.assertIn('data-product-bootstrap-wave73="1"', html)
        self.assertIn('data-product-entry-wave73="1"', html)
        self.assertNotIn('data-product-entry-wave72="1"', html)
        self.assertLess(html.index('/product-bootstrap.js'), html.index('/product-entry-wave73.js'))
        for name in UI_ASSETS:
            with self.subTest(name=name):
                with urlopen(self.base + "/" + name, timeout=10) as response:
                    self.assertEqual(response.status, 200)
                    self.assertGreater(len(response.read()), 0)

    def test_bootstrap_declares_complete_late_wave_chain(self):
        bootstrap = (ROOT / "web/product-bootstrap.js").read_text(encoding="utf-8")
        for name in REQUIRED_WEB_ASSETS[7:-1]:
            with self.subTest(name=name):
                self.assertIn(f"/{name}", bootstrap)
        self.assertIn("/product-journey.js", bootstrap)
        self.assertNotIn("setInterval", bootstrap)
        self.assertIn("wave73BootstrapPromise", bootstrap)
        entry = (ROOT / "web/product-entry-wave73.js").read_text(encoding="utf-8")
        self.assertIn("await globalThis.wave73BootstrapPromise", entry)
        self.assertIn("/product-entry.js", entry)

    def test_ui_integrity_and_company_scoped_journey_contract(self):
        status, before = self._json("/api/ui-integrity")
        self.assertEqual(status, 200)
        self.assertTrue(before["ready"], before["missing"])
        self.assertTrue(before["deterministic_bootstrap"])
        self.assertEqual(before["inventory"]["present_ui_assets"], len(UI_ASSETS))
        self.assertEqual(before["inventory"]["declared_views"], len(UI_VIEWS))
        status, company = self._post("/api/companies", {"name": "Greenatics Wave 73"})
        self.assertEqual(status, 201)
        status, report = self._json(f"/api/ui-integrity?company_id={company['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(report["ready"], report["missing"])
        self.assertEqual(report["company"]["id"], company["id"])
        self.assertEqual([row["id"] for row in report["views"]], list(UI_VIEWS))
        self.assertTrue(report["safety"]["read_only_projection"])
        self.assertFalse(report["safety"]["browser_check_executes_external_actions"])

    def test_browser_journey_is_navigation_only(self):
        journey = (ROOT / "web/product-journey.js").read_text(encoding="utf-8")
        for view in UI_VIEWS:
            self.assertIn(f"'{view}'", journey)
        self.assertIn("wave73RunJourneyCheck", journey)
        self.assertIn("Verificar interfaz", journey)
        self.assertNotIn("fetch(", journey)
        self.assertNotIn(".submit(", journey)
        self.assertNotIn(".click(", journey)
        self.assertNotIn("setInterval", journey)
        self.assertIn("submittedForms:false", journey)
        self.assertIn("externalActions:false", journey)

    def test_release_and_workflow_boundary_stays_non_authoritative(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src/binario_marketing/service_wave73_app.py").read_text(encoding="utf-8")
        self.assertNotIn("RELEASE_READY = True", service)


if __name__ == "__main__":
    unittest.main()
