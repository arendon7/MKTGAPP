import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave52_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave52LearningHttpUiTests(unittest.TestCase):
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
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(self.base + path, method=method, data=data, headers={"Content-Type": "application/json"} if data else {})
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_learning_bundle_and_local_get_are_served(self):
        with urlopen(self.base + "/learning-loop.js", timeout=5) as response:
            text = response.read().decode("utf-8")
        self.assertIn("ANALYTICS & LEARNING LOOP", text)
        self.assertIn("Actualizar resultados desde Meta", text)
        self.assertIn("Registrar decisión local", text)
        status, payload = self.request_json(f"/api/companies/{self.company['id']}/learning")
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema"], "binario.marketing.learning-loop.v1")
        self.assertIsNone(payload["latest_snapshot"])
        self.assertFalse(payload["safety"]["provider_refresh_performed"])
        self.assertFalse(payload["attribution"]["crm_to_campaign"])

    def test_refresh_route_is_explicit_and_persists_snapshot(self):
        calls = []
        self.runtime.social_analytics_meta = lambda company_id, limit=20: calls.append((company_id, limit)) or {
            "configured": False,
            "coverage": {"eligible": 0, "requested": 0, "observed": 0, "measured": 0, "errors": 0},
            "totals": {}, "observations": [],
        }
        self.runtime.company_paid_media = lambda company_id: []
        status, payload = self.request_json(
            f"/api/companies/{self.company['id']}/learning/refresh",
            method="POST",
            body={"date_preset": "last_7d"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(len(calls), 1)
        self.assertIsNotNone(payload["latest_snapshot"])
        self.assertTrue(payload["safety"]["provider_refresh_performed"])
        status, local = self.request_json(f"/api/companies/{self.company['id']}/learning")
        self.assertEqual(status, 200)
        self.assertEqual(local["latest_snapshot"]["id"], payload["latest_snapshot"]["id"])
        self.assertFalse(local["safety"]["provider_refresh_performed"])

    def test_source_has_no_polling_activation_or_automatic_decision_execution(self):
        ui = (ROOT / "web" / "learning-loop.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave52_app.py").read_text(encoding="utf-8")
        store = (ROOT / "src" / "binario_marketing" / "learning_store.py").read_text(encoding="utf-8")
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("/activate", ui)
        self.assertNotIn("publish-now", ui)
        self.assertNotIn("status:'ACTIVE'", ui.replace('"', "'"))
        self.assertIn('"provider_mutation_performed": False', service)
        self.assertIn('"decision_execution_performed": False', service)
        self.assertIn("never executes the decision", store)

    def test_loader_and_current_builder_chain_wave52_after_wave51(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("ai.addEventListener('load',loadLearningLoop", loader)
        self.assertIn("learning.src='/learning-loop.js'", loader)
        self.assertIn("service_wave52_app", builder)
        self.assertIn("audit_wave52_learning_loop.sh", builder)
        self.assertIn("Wave 52", builder)


if __name__ == "__main__":
    unittest.main()
