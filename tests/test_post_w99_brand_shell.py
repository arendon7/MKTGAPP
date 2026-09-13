from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_brand_shell_app import AppRuntime, _brand_index, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PostW99BrandShellTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_root_is_branded_before_javascript_runs(self):
        with urlopen(self.root + "/", timeout=5) as response:
            body = response.read().decode("utf-8")
            content_type = response.headers.get("Content-Type", "")
        self.assertTrue(content_type.startswith("text/html"))
        self.assertIn("<title>MERCADEO APP · Centro de operaciones</title>", body)
        self.assertIn('name="application-name" content="MERCADEO APP"', body)
        self.assertIn('name="description" content="Centro local multiempresa para operaciones de marketing."', body)
        self.assertIn('rel="icon" type="image/svg+xml" href="/mercadeo-app-icon.svg"', body)
        self.assertIn('<p class="eyebrow">MERCADEO APP</p><h1>Centro de operaciones</h1>', body)
        for legacy in ("BINARIO Marketing", "SISTEMA BINARIO", "Marketing Workspace"):
            self.assertNotIn(legacy, body)

    def test_brand_transform_fails_closed_if_source_contract_drifts(self):
        with self.assertRaisesRegex(ValueError, "source contract changed"):
            _brand_index("<html><title>Different product</title></html>")

    def test_svg_favicon_is_local_static_and_script_free(self):
        for path in ("/mercadeo-app-icon.svg", "/favicon.ico"):
            with self.subTest(path=path):
                with urlopen(self.root + path, timeout=5) as response:
                    body = response.read().decode("utf-8")
                    content_type = response.headers.get("Content-Type", "")
                self.assertTrue(content_type.startswith("image/svg+xml"))
                self.assertIn("<title id=\"title\">MERCADEO APP</title>", body)
                self.assertIn("viewBox=\"0 0 64 64\"", body)
                self.assertIn('xmlns="http://www.w3.org/2000/svg"', body)
                for forbidden in ("<script", "https://", "data:", "<image", "xlink:href", 'href="http'):
                    self.assertNotIn(forbidden, body)

    def test_brand_terminal_is_presentation_only_and_preserves_language_polish(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_brand_shell_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_health_summary_app as base", service)
        self.assertIn("mercadeo-app-icon.svg", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_language_polish_app", dev)
        self.assertIn("service_post_w99_pilot_health_summary_app", dev)
        self.assertIn("service_post_w99_brand_shell_app", dev)
        polish = (ROOT / "web" / "pilot-language-polish.js").read_text(encoding="utf-8")
        self.assertIn("MERCADEO APP · Centro de operaciones", polish)

    def test_release_boundary_and_documentation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        docs = (ROOT / "docs" / "POST_W99_BRAND_SHELL.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("presentation-only", docs.casefold())
        self.assertIn("not production readiness", docs.casefold())
        self.assertIn("first html response", docs.casefold())
        self.assertIn("favicon", docs.casefold())


if __name__ == "__main__":
    unittest.main()
