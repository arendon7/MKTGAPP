import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_execution_return_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PostW99ExecutionReturnTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Execution Return Co"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_runtime_preserves_today_and_prior_post_w99_surfaces(self):
        company_id = self.company["id"]
        self.assertEqual(self.runtime.today_execution(company_id)["schema"], "binario.marketing.today-execution.v1")
        self.assertEqual(self.runtime.executive_cockpit(company_id)["schema"], "binario.marketing.executive-cockpit.v1")
        self.assertEqual(self.runtime.portfolio_control_tower()["schema"], "binario.marketing.portfolio-control-tower.v1")
        self.assertEqual(self.runtime.action_center(company_id)["schema"], "binario.marketing.action-center.v1")

    def test_http_bootstrap_loads_execution_return_after_today(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/today-execution.js", timeout=5) as response:
                today_source = response.read().decode("utf-8")
            self.assertIn("execution-return.js", today_source)
            self.assertIn("data-post-w99-execution-return", today_source)

            with urlopen(base + "/execution-return.js", timeout=5) as response:
                return_source = response.read().decode("utf-8")
            self.assertIn("binario.marketing.execution-return.v1", return_source)
            self.assertIn("sessionStorage", return_source)
            self.assertIn("Volver y releer plan", return_source)

            with urlopen(base + f"/api/companies/{self.company['id']}/today-execution", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.today-execution.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_browser_context_is_ephemeral_navigation_only(self):
        source = (ROOT / "web" / "execution-return.js").read_text(encoding="utf-8")
        self.assertIn("sessionStorage.setItem", source)
        self.assertIn("sessionStorage.removeItem", source)
        self.assertNotIn("localStorage.setItem", source)
        self.assertIn("company_id", source)
        self.assertIn("action_id", source)
        self.assertIn("destination", source)
        self.assertIn("executionReturnCurrentMatches", source)
        self.assertIn("actionCenterOpen({action:context.destination})", source)

    def test_return_rechecks_full_action_center_before_interpreting_visibility(self):
        source = (ROOT / "web" / "execution-return.js").read_text(encoding="utf-8")
        self.assertIn("actionCenterLoad(true)", source)
        self.assertIn("todayLoad(true)", source)
        self.assertIn("STILL_IN_TODAY", source)
        self.assertIn("STILL_PENDING", source)
        self.assertIn("NO_LONGER_PENDING", source)
        self.assertIn("canonicalIndex", source)
        self.assertIn("todayIndex", source)
        self.assertIn("Esto no se interpreta por sí solo", source)

    def test_execution_return_adds_no_business_mutation_or_background_loop(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_execution_return_app.py").read_text(encoding="utf-8")
        source = (ROOT / "web" / "execution-return.js").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_today_execution_app as base", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertNotIn("def do_PUT", service)
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", "setInterval", "sendBeacon"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("fetch(", source)

    def test_docs_make_absence_non_equivalent_to_completion(self):
        doc = (ROOT / "docs" / "POST_W99_EXECUTION_RETURN.md").read_text(encoding="utf-8")
        self.assertIn("does **not** claim that the task was completed", doc)
        self.assertIn("sessionStorage", doc)
        self.assertIn("Action Center remains priority authority", doc)
        self.assertIn("owner module remains completion authority", doc)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("not W100", doc)


if __name__ == "__main__":
    unittest.main()
