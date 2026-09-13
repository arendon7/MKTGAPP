from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_pilot_month_tracker_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotMonthTrackerTests(unittest.TestCase):
    def test_tracker_is_explicit_read_only_and_uses_existing_receipt_api(self):
        source = (ROOT / "web" / "pilot-month-tracker.js").read_text(encoding="utf-8")
        self.assertIn("Seguimiento 30 días", source)
        self.assertIn("/api/pilot/daily-receipts?limit=365", source)
        self.assertIn("method:'GET'", source)
        self.assertIn("recentDates(30)", source)
        self.assertIn("LISTO", source)
        self.assertIn("ATENCIÓN", source)
        self.assertIn("SIN REGISTRO", source)
        self.assertIn("post-w99-pilot-launch-gate-rendered", source)
        for forbidden in (
            "method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'",
            "X-Mercadeo-Operator", "localStorage", "sessionStorage", "setInterval(",
            "MutationObserver", "/api/meta/", "MetaGraphClient", "AIProviderClient",
            "publish-now", "restoreSnapshot", "createSnapshot",
        ):
            self.assertNotIn(forbidden, source)

    def test_tracker_derives_observation_without_claiming_failure_or_execution(self):
        source = (ROOT / "web" / "pilot-month-tracker.js").read_text(encoding="utf-8")
        self.assertIn("latest.has(key)", source)
        self.assertIn("currentStreak", source)
        self.assertIn("missing", source)
        self.assertIn("Un día sin recibo significa", source)
        self.assertIn("no una falla de la aplicación", source)
        self.assertNotIn("production_ready", source)
        self.assertNotIn("release_authority", source)

    def test_http_chain_serves_tracker_after_daily_receipt_and_keeps_existing_get(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(root + "/pilot-daily-receipt.js", timeout=5) as response:
                    daily = response.read().decode("utf-8")
                self.assertIn("pilot-daily-receipt", daily)
                self.assertIn("/pilot-month-tracker.js", daily)
                with urlopen(root + "/pilot-month-tracker.js", timeout=5) as response:
                    tracker = response.read().decode("utf-8")
                self.assertIn("Seguimiento 30 días", tracker)
                with urlopen(root + "/api/pilot/daily-receipts?limit=365", timeout=5) as response:
                    history = response.read().decode("utf-8")
                self.assertIn("binario.marketing.pilot-daily-receipts.v1", history)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown()
                runtime.transcriptions.shutdown()
                runtime.renders.shutdown()

    def test_terminal_and_release_separation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_month_tracker_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_daily_receipt_app as base", service)
        self.assertIn("/pilot-month-tracker.js", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_daily_receipt_app", dev)
        self.assertIn("service_post_w99_pilot_month_tracker_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_MONTH_TRACKER.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production readiness", docs.casefold())
        self.assertIn("no business api", docs.casefold())
        self.assertIn("physical apple silicon uat", docs.casefold())


if __name__ == "__main__":
    unittest.main()
