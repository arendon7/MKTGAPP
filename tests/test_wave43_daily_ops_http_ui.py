import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave43_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave43DailyOpsHttpUiTests(unittest.TestCase):
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

    def test_daily_bundle_is_served(self):
        with urlopen(self.base + "/daily-ops.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("HOY · PRIORIDADES", ui)

    def test_loader_waits_for_wave41_and_wave42_dom_readiness(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("#inbox-wave39-style", loader)
        self.assertIn("#inbox-replies-wave41-style", loader)
        self.assertIn("#editorial-wave42-style", loader)
        self.assertIn("daily.src='/daily-ops.js'", loader)
        self.assertIn("editorial.addEventListener('load',loadDaily", loader)
        self.assertNotIn("globalThis.editorialState", loader)
        self.assertNotIn("globalThis.inboxReplyState", loader)

    def test_mac_build_launches_wave43_after_wave42_and_audits_it(self):
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave42_app import serve", build)
        self.assertIn("service_wave43_app import serve", build)
        self.assertLess(build.index("service_wave42_app import serve"), build.index("service_wave43_app import serve"))
        self.assertIn("audit_wave43_daily_ops.sh", build)


if __name__ == "__main__":
    unittest.main()
