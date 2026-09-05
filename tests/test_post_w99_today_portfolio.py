import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_social_background_control_app import AppRuntime as ParentRuntime
from binario_marketing.service_post_w99_today_portfolio_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class TodayPortfolioTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_extends_background_control_runtime(self):
        self.assertTrue(issubclass(AppRuntime, ParentRuntime))

    def test_http_bootstrap_serves_today_portfolio_and_inherited_portfolio_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                background = urlopen(root + "/social-background-control.js", timeout=5).read().decode("utf-8")
                browser = urlopen(root + "/today-portfolio.js", timeout=5).read().decode("utf-8")
                portfolio = json.loads(urlopen(root + "/api/portfolio-control-tower", timeout=5).read().decode("utf-8"))
                self.assertIn("/today-portfolio.js", background)
                self.assertIn("data-post-w99-today-portfolio", background)
                self.assertIn("/api/portfolio-control-tower", browser)
                self.assertEqual(portfolio["schema"], "binario.marketing.portfolio-control-tower.v1")
                self.assertTrue(portfolio["safety"]["read_only_projection"])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_browser_uses_existing_portfolio_order_and_caps_focus_at_five(self):
        browser = (ROOT / "web" / "today-portfolio.js").read_text(encoding="utf-8")
        self.assertIn("const queue=(p.queue||[]).slice(0,5)", browser)
        self.assertNotIn(".sort(", browser)
        self.assertIn("Portfolio Control Tower", browser)
        self.assertIn("Action Center", browser)
        self.assertIn("El orden viene de Action Center", browser)
        self.assertNotIn("score", browser.lower())
        self.assertNotIn("forecast", browser.lower())

    def test_cross_company_navigation_switches_company_before_owner_view(self):
        browser = (ROOT / "web" / "today-portfolio.js").read_text(encoding="utf-8")
        body = browser.split("async function todayPortfolioOpen(row)", 1)[1].split("function todayPortfolioButton", 1)[0]
        self.assertIn("portfolioNavigate", body)
        self.assertIn("marketingOpsState.selectedCompanyId=companyId", body)
        self.assertIn("refreshMarketingOps", body)
        self.assertIn("opsShowView(row.action.view)", body)
        self.assertLess(body.index("marketingOpsState.selectedCompanyId=companyId"), body.index("opsShowView(row.action.view)"))

    def test_company_mode_is_explicit_and_reversible(self):
        browser = (ROOT / "web" / "today-portfolio.js").read_text(encoding="utf-8")
        self.assertIn("mode:'PORTFOLIO'", browser)
        self.assertIn("mode='COMPANY'", browser)
        self.assertIn("Volver a todas las empresas", browser)
        self.assertIn("Ver empresa activa", browser)

    def test_browser_has_no_business_mutation_polling_or_synthetic_execution(self):
        browser = (ROOT / "web" / "today-portfolio.js").read_text(encoding="utf-8")
        self.assertNotIn("method:'POST'", browser)
        self.assertNotIn('method:"POST"', browser)
        self.assertNotIn("method:'PATCH'", browser)
        self.assertNotIn("method:'DELETE'", browser)
        self.assertNotIn("setInterval(", browser)
        self.assertNotIn("setTimeout(", browser)
        self.assertNotIn(".click()", browser)
        self.assertNotIn("/publish", browser)
        self.assertNotIn("/send", browser)

    def test_dev_terminal_advances_to_today_portfolio_and_keeps_parent_breadcrumb(self):
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_today_portfolio_app", entrypoint)
        self.assertIn("_SocialBackgroundControlAppRuntime", entrypoint)
        self.assertNotIn("from .service import", entrypoint)

    def test_release_boundary_remains_post_w99_only(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_today_portfolio_app.py").read_text(encoding="utf-8")
        browser = (ROOT / "web" / "today-portfolio.js").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_social_background_control_app", service)
        self.assertNotIn("release_authority", browser)
        self.assertNotIn("physical_uat", browser)
        self.assertNotIn("v0.9.0", browser)


if __name__ == "__main__":
    unittest.main()
