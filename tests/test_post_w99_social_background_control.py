import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from unittest.mock import patch

from binario_marketing.service_post_w99_primary_navigation_app import AppRuntime as ParentRuntime
from binario_marketing.service_post_w99_social_background_control_app import AppRuntime, create_server
from binario_marketing.social_background import BackgroundAgentStatus


ROOT = Path(__file__).resolve().parents[1]


class SocialBackgroundControlTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_extends_primary_navigation_runtime(self):
        self.assertTrue(issubclass(AppRuntime, ParentRuntime))

    def test_http_bootstrap_loads_calendar_background_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                navigation = urlopen(root + "/primary-navigation.js", timeout=5).read().decode("utf-8")
                control = urlopen(root + "/social-background-control.js", timeout=5).read().decode("utf-8")
                self.assertIn("/social-background-control.js", navigation)
                self.assertIn("data-post-w99-social-background-control", navigation)
                self.assertIn("renderOpsCalendar", control)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_status_endpoint_is_read_only_and_returns_agent_plus_last_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            fake = {
                "agent": {
                    "platform_supported": True,
                    "installed": False,
                    "loaded": False,
                    "stale": False,
                    "plist_path": "/tmp/fake.plist",
                    "app_bundle": None,
                    "interval_seconds": 60,
                },
                "last_run": None,
            }
            try:
                with patch(
                    "binario_marketing.service_post_w99_social_background_control_app.social_background_overview",
                    return_value=fake,
                ):
                    payload = json.loads(urlopen(root + "/api/social/background", timeout=5).read().decode("utf-8"))
                self.assertEqual(payload, fake)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_explicit_http_install_and_delete_delegate_once_and_return_overview(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            enabled = BackgroundAgentStatus(True, True, True, False, "/tmp/a.plist", "/tmp/App.app", 60)
            disabled = BackgroundAgentStatus(True, False, False, False, "/tmp/a.plist", None, 60)
            enabled_overview = {"agent": {"installed": True, "loaded": True}, "last_run": None}
            disabled_overview = {"agent": {"installed": False, "loaded": False}, "last_run": None}
            try:
                with patch(
                    "binario_marketing.service_post_w99_social_background_control_app.install_social_background",
                    return_value=enabled,
                ) as install, patch(
                    "binario_marketing.service_post_w99_social_background_control_app.social_background_overview",
                    return_value=enabled_overview,
                ):
                    request = Request(
                        root + "/api/social/background/install",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    payload = json.loads(urlopen(request, timeout=5).read().decode("utf-8"))
                    self.assertEqual(payload, enabled_overview)
                    install.assert_called_once_with()

                with patch(
                    "binario_marketing.service_post_w99_social_background_control_app.uninstall_social_background",
                    return_value=disabled,
                ) as uninstall, patch(
                    "binario_marketing.service_post_w99_social_background_control_app.social_background_overview",
                    return_value=disabled_overview,
                ):
                    request = Request(root + "/api/social/background", method="DELETE")
                    payload = json.loads(urlopen(request, timeout=5).read().decode("utf-8"))
                    self.assertEqual(payload, disabled_overview)
                    uninstall.assert_called_once_with()
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_browser_control_is_explicit_and_has_no_polling_or_auto_install(self):
        browser = (ROOT / "web" / "social-background-control.js").read_text(encoding="utf-8")
        self.assertIn("window.confirm", browser)
        self.assertIn("/api/social/background/install", browser)
        self.assertIn("method:'DELETE'", browser)
        self.assertIn("publicación en segundo plano", browser.lower())
        self.assertNotIn("setInterval(", browser)
        self.assertNotIn("setTimeout(", browser)
        load_body = browser.split("async function socialBackgroundLoad()", 1)[1].split("function socialBackgroundStateLabel", 1)[0]
        self.assertIn("opsApi('/api/social/background')", load_body)
        self.assertNotIn("/install", load_body)
        self.assertNotIn("method:'DELETE'", load_body)

    def test_dev_terminal_advances_without_touching_canonical_release_service(self):
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_social_background_control_app", entrypoint)
        self.assertIn("_PrimaryNavigationAppRuntime", entrypoint)
        self.assertNotIn("from .service import", entrypoint)


if __name__ == "__main__":
    unittest.main()
