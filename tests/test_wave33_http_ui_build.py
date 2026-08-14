import json
import platform
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave33 import AppRuntime, create_server
from binario_marketing.social_process_lock import social_queue_lock


ROOT = Path(__file__).resolve().parents[1]


def request_json(url, *, method="GET", payload=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method, headers=headers)
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class Wave33HttpTests(unittest.TestCase):
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

    def test_background_status_is_read_only_and_locked_scheduler_is_active(self):
        status_code, payload = request_json(self.base + "/api/background-scheduling")
        self.assertEqual(status_code, 200)
        expected_supported = platform.system() == "Darwin" and int((platform.mac_ver()[0] or "0").split(".", 1)[0]) >= 13
        self.assertEqual(payload["supported"], expected_supported)
        self.assertFalse(payload["helper_available"])
        self.assertTrue(payload["desktop_scheduler"]["process_lock"])
        self.assertEqual(payload["queue"], {"queued": 0, "publishing": 0, "failed": 0})

    def test_unsupported_registration_fails_without_touching_queue(self):
        company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.update_company(company["id"], {"facebook_page_id": "page-1"})
        row = self.runtime.create_company_publication(company["id"], {
            "channel": "facebook_page",
            "kind": "text",
            "message": "Programada",
            "scheduled_for": "2030-01-02T12:00:00+00:00",
        })
        before = self.runtime.social.get(row["id"])
        request = Request(
            self.base + "/api/background-scheduling/register",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 409)
        after = self.runtime.social.get(row["id"])
        self.assertEqual(after, before)

    def test_explicit_company_publish_fails_before_provider_when_queue_owned(self):
        company = self.runtime.create_company({"name": "Sistema Binario"})
        self.runtime.update_company(company["id"], {"facebook_page_id": "page-2"})
        row = self.runtime.create_company_publication(company["id"], {
            "channel": "facebook_page",
            "kind": "text",
            "message": "Lock guard",
        })
        with social_queue_lock(self.runtime.social.root, timeout=0.0) as acquired:
            self.assertTrue(acquired)
            with self.assertRaisesRegex(ValueError, "queue is busy"):
                self.runtime.publish_company_publication_now(company["id"], row["id"])
        self.assertEqual(self.runtime.social.get(row["id"]).status, "DRAFT")

    def test_background_ui_bundle_is_served(self):
        with urlopen(self.base + "/background-scheduling.js", timeout=5) as response:
            js = response.read().decode("utf-8")
        for required in (
            "PROGRAMACIÓN EN SEGUNDO PLANO",
            "REQUIERE APROBACIÓN",
            "Activar",
            "Desactivar",
            "Abrir Login Items",
            "best effort",
        ):
            self.assertIn(required, js)


class Wave33UiAndBuildContractTests(unittest.TestCase):
    def test_ui_is_explicit_opt_in_and_never_auto_registers(self):
        js = (ROOT / "web" / "background-scheduling.js").read_text(encoding="utf-8")
        loader = (ROOT / "web" / "instagram-local-reel.js").read_text(encoding="utf-8")
        self.assertIn("opsApi('/api/background-scheduling'", js)
        self.assertIn("opsApi(`/api/background-scheduling/${action}`", js)
        self.assertIn("method:'DELETE'", js)
        self.assertIn("backgroundMutate('register')", js)
        self.assertIn("backgroundMutate('unregister')", js)
        self.assertIn("script.src='/marketing-ops.js'", loader)
        self.assertIn("crm.src='/crm.js'", loader)
        self.assertIn("bg.src='/background-scheduling.js'", loader)
        self.assertNotIn("setInterval(()=>backgroundMutate", js)
        self.assertNotIn("MutationObserver(()=>backgroundMutate", js)
        self.assertNotIn("/create-paused", js)
        self.assertNotIn("activate", js.lower())

    def test_background_agent_has_no_workspace_or_secret_persistence(self):
        source = (ROOT / "src" / "binario_marketing" / "background_social_agent.py").read_text(encoding="utf-8")
        for forbidden in ("Workspace", "timeline.append", "access_token", "upload_uri", "data_root\":"):
            self.assertNotIn(forbidden, source)
        self.assertIn("State\" / \"social", source)
        self.assertIn("background_social", source)

    def test_mac_builder_uses_native_agent_and_smappservice_bundle_contract(self):
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        background = (ROOT / "scripts" / "build_background_scheduler.sh").read_text(encoding="utf-8")
        launcher = (ROOT / "native" / "main_launcher.c").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_full_mac_app.sh").read_text(encoding="utf-8")
        helper = (ROOT / "native" / "background_service_helper.swift").read_text(encoding="utf-8")
        self.assertIn("from binario_marketing.service_wave33 import serve", build)
        self.assertLess(build.index("build_background_scheduler.sh"), build.index("build_native_main_launcher.sh"))
        self.assertLess(build.index("build_native_main_launcher.sh"), build.index("codesign --force --deep"))
        self.assertIn("background_agent_launcher.c", background)
        self.assertIn("Contents/MacOS/binario-background-agent", background)
        self.assertIn("Library/LaunchAgents", background)
        self.assertIn("<key>StartInterval</key><integer>60</integer>", background)
        self.assertNotIn("#!/bin/bash\nset -euo pipefail\nHERE=", background)
        self.assertIn('SMAppService.agent(plistName: plistName)', helper)
        self.assertIn("BINARIO_BACKGROUND_SERVICE_HELPER", launcher)
        self.assertIn("BACKGROUND AGENT ONE-SHOT PASS", audit)
        self.assertIn("not-found", audit)
        self.assertIn("service_wave33 import AppRuntime", audit)


if __name__ == "__main__":
    unittest.main()