import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_integrated_cockpit_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PostW99PortfolioExecutiveIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company_a = self.runtime.create_company({"name": "Empresa A"})
        self.company_b = self.runtime.create_company({"name": "Empresa B"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_terminal_runtime_exposes_both_levels(self):
        portfolio = self.runtime.portfolio_control_tower()
        cockpit = self.runtime.executive_cockpit(self.company_a["id"])
        self.assertEqual(portfolio["schema"], "binario.marketing.portfolio-control-tower.v1")
        self.assertEqual(cockpit["schema"], "binario.marketing.executive-cockpit.v1")
        self.assertEqual(cockpit["company"]["id"], self.company_a["id"])
        self.assertEqual(portfolio["summary"]["active_companies"], 2)

    def test_http_chain_serves_portfolio_then_bootstraps_executive(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/decision-review.js", timeout=5) as response:
                decision_bootstrap = response.read().decode("utf-8")
            self.assertIn("portfolio-control-tower.js", decision_bootstrap)
            self.assertIn("data-post-w99-portfolio-control-tower", decision_bootstrap)

            with urlopen(base + "/portfolio-control-tower.js", timeout=5) as response:
                portfolio_bootstrap = response.read().decode("utf-8")
            self.assertIn("executive-cockpit.js", portfolio_bootstrap)
            self.assertIn("data-post-w99-executive-cockpit", portfolio_bootstrap)

            with urlopen(base + "/api/portfolio-control-tower", timeout=5) as response:
                portfolio = json.loads(response.read().decode("utf-8"))
            with urlopen(base + f"/api/companies/{self.company_a['id']}/executive-cockpit", timeout=5) as response:
                cockpit = json.loads(response.read().decode("utf-8"))
            self.assertEqual(portfolio["schema"], "binario.marketing.portfolio-control-tower.v1")
            self.assertEqual(cockpit["schema"], "binario.marketing.executive-cockpit.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_integrated_handler_remains_get_only(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_integrated_cockpit_app.py").read_text(encoding="utf-8")
        self.assertNotIn("def do_POST", source)
        self.assertNotIn("def do_PATCH", source)
        self.assertNotIn("def do_DELETE", source)
        self.assertIn("service_post_w99_portfolio_control_tower_app as base", source)
        self.assertIn("compose_executive_cockpit", source)

    def test_no_release_files_are_required_by_integration(self):
        doc = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("Portfolio Control Tower", doc)
        self.assertIn("Executive Marketing Cockpit", doc)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)


if __name__ == "__main__":
    unittest.main()
