import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_operator_session_evidence_integration_app as parent
from binario_marketing.service_post_w99_primary_navigation_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PrimaryNavigationTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_session_evidence_parent(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_http_bootstrap_loads_primary_navigation_after_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Primary Navigation HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(
                    root + "/operator-session-evidence-integration.js", timeout=5
                ).read().decode("utf-8")
                navigation = urlopen(root + "/primary-navigation.js", timeout=5).read().decode("utf-8")
                self.assertIn("/primary-navigation.js", parent_js)
                self.assertIn("data-post-w99-primary-navigation", parent_js)
                self.assertIn("POST_W99_PRIMARY_NAVIGATION", navigation)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_primary_row_is_exactly_the_seven_operator_destinations(self):
        browser = (ROOT / "web" / "primary-navigation.js").read_text(encoding="utf-8")
        primary_decl = browser.split("const POST_W99_SECONDARY_NAVIGATION=", 1)[0]
        expected = (
            ("today-execution", "Hoy"),
            ("companies", "Empresas"),
            ("content", "Contenido"),
            ("calendar", "Calendario"),
            ("crm", "CRM"),
            ("inbox", "Inbox"),
            ("intelligence", "Resultados"),
        )
        for view, label in expected:
            self.assertIn(f"['{view}','{label}']", primary_decl)
        self.assertEqual(primary_decl.count("['"), 7)

    def test_specialist_modules_remain_reachable_from_more(self):
        browser = (ROOT / "web" / "primary-navigation.js").read_text(encoding="utf-8")
        for view in (
            "executive-cockpit",
            "action-center",
            "campaigns",
            "pauta",
            "publish",
            "video",
            "audiences",
            "analytics",
        ):
            self.assertIn(f"['{view}'", browser)
        self.assertIn("Más", browser)

    def test_astra_is_permanent_but_does_not_generate_automatically(self):
        browser = (ROOT / "web" / "primary-navigation.js").read_text(encoding="utf-8")
        self.assertIn("✦ Astra / IA", browser)
        self.assertIn("primaryNavigationOpenAstra", browser)
        self.assertIn(".w51-ai", browser)
        self.assertNotIn("/ai/generate", browser)

    def test_navigation_layer_has_no_business_io_or_persistence(self):
        service = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_primary_navigation_app.py"
        ).read_text(encoding="utf-8")
        browser = (ROOT / "web" / "primary-navigation.js").read_text(encoding="utf-8")
        for forbidden in (
            "fetch(",
            "opsApi(",
            "XMLHttpRequest",
            "sendBeacon",
            "localStorage",
            "sessionStorage",
            "setInterval(",
        ):
            self.assertNotIn(forbidden, browser)
        for forbidden in ("def do_POST", "def do_PATCH", "def do_PUT", "def do_DELETE"):
            self.assertNotIn(forbidden, service)

    def test_navigation_is_rebuilt_idempotently_without_deleting_owner_views(self):
        browser = (ROOT / "web" / "primary-navigation.js").read_text(encoding="utf-8")
        self.assertIn("nav.replaceChildren()", browser)
        self.assertIn("opsShowView", browser)
        self.assertIn("opsShowLegacy", browser)
        self.assertNotIn("remove()", browser)

    def test_docs_and_dev_terminal_preserve_frozen_w99_boundary(self):
        docs = (ROOT / "docs" / "POST_W99_PRIMARY_NAVIGATION.md").read_text(encoding="utf-8")
        entrypoint = (
            ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py"
        ).read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No es W100", docs)
        self.assertIn("service_post_w99_primary_navigation_app", entrypoint)
        self.assertIn("service_post_w99_operator_session_evidence_integration_app", entrypoint)


if __name__ == "__main__":
    unittest.main()
