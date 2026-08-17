import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave44_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave44DailyActionsHttpUiTests(unittest.TestCase):
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

    def test_daily_actions_bundle_is_served(self):
        with urlopen(self.base + "/daily-actions.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
            status = response.status
        self.assertEqual(status, 200)
        self.assertIn("dailyActionCompleteActivity", ui)
        self.assertIn("Gestionar", ui)

    def test_loader_orders_wave44_after_wave43(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("daily.src='/daily-ops.js'", loader)
        self.assertIn("actions.src='/daily-actions.js'", loader)
        self.assertIn("daily.addEventListener('load',loadDailyActions", loader)
        self.assertIn("#daily-ops-wave43-style", loader)

    def test_mac_build_launches_and_audits_wave44(self):
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave43_app import serve", build)
        self.assertIn("service_wave44_app import serve", build)
        self.assertLess(build.index("service_wave43_app import serve"), build.index("service_wave44_app import serve"))
        self.assertIn("audit_wave44_daily_actions.sh", build)


if __name__ == "__main__":
    unittest.main()
