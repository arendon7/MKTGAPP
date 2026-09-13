from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_pilot_readiness_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotReadinessRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_http_entry_has_pilot_identity_and_assets(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/", timeout=5) as response:
                html = response.read().decode("utf-8")
            self.assertIn("<title>MERCADEO APP · Centro de operaciones</title>", html)
            self.assertIn('href="/favicon.svg"', html)
            self.assertIn('src="/pilot-readiness.js"', html)
            self.assertIn('<p class="eyebrow">MERCADEO APP</p><h1>Centro de operaciones</h1>', html)
            self.assertNotIn("<title>BINARIO Marketing</title>", html)

            with urlopen(root + "/favicon.svg", timeout=5) as response:
                favicon = response.read().decode("utf-8")
                content_type = response.headers.get("Content-Type", "")
            self.assertIn("image/svg+xml", content_type)
            self.assertIn("<svg", favicon)
            self.assertIn("MERCADEO APP", favicon)

            with urlopen(root + "/pilot-readiness.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_PILOT_READINESS", source)
            self.assertIn("Piloto local", source)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_pilot_browser_contract_routes_first_run_without_business_mutation(self):
        source = (ROOT / "web" / "pilot-readiness.js").read_text(encoding="utf-8")
        for required in (
            "MERCADEO APP · Centro de operaciones",
            "wave73-bootstrap-failed",
            "marketing-ops-refreshed",
            "opsShowView('companies')",
            "opsShowView('today-execution')",
            "Piloto local",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "method:'POST'", "method:'PATCH'", "method:'DELETE'", "/api/meta/",
            "setInterval(", "MutationObserver", "publish-now", "MetaGraphClient", "AIProviderClient",
        ):
            self.assertNotIn(forbidden, source)

    def test_terminal_alias_and_release_separation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_readiness_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_companies_app as base", service)
        self.assertIn("/pilot-readiness.js", service)
        self.assertIn("/favicon.svg", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_readiness_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_READINESS.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("serve-dev", docs)
        self.assertIn("not production", docs.casefold())


if __name__ == "__main__":
    unittest.main()
