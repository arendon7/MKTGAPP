import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave42_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave42EditorialHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.update_company(self.company["id"], {"facebook_page_id": "page-1"})
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

    def test_replace_route_and_existing_cancel_route_work_company_scoped(self):
        old = self.runtime.create_company_publication(self.company["id"], {
            "channel": "facebook_page", "kind": "text", "message": "Original",
            "scheduled_for": (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(),
        })
        payload = {"message": "Revisado", "scheduled_for": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()}
        request = Request(
            self.base + f"/api/companies/{self.company['id']}/publications/{old['id']}/replace",
            data=json.dumps(payload).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 201)
        self.assertEqual(result["previous"]["status"], "CANCELLED")
        self.assertEqual(result["replacement"]["status"], "QUEUED")
        cancel = Request(
            self.base + f"/api/companies/{self.company['id']}/publications/{result['replacement']['id']}",
            method="DELETE", headers={"Accept": "application/json"},
        )
        with urlopen(cancel, timeout=5) as response:
            cancelled = json.loads(response.read().decode("utf-8"))
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_replace_route_rejects_identity_mutation(self):
        old = self.runtime.create_company_publication(self.company["id"], {"channel": "facebook_page", "kind": "text", "message": "Original"})
        request = Request(
            self.base + f"/api/companies/{self.company['id']}/publications/{old['id']}/replace",
            data=json.dumps({"message": "Cambio", "channel": "instagram"}).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 400)
        self.assertEqual(self.runtime.social.get(old["id"]).status, "DRAFT")

    def test_editorial_bundle_is_served_and_explicit_only(self):
        with urlopen(self.base + "/editorial-management.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        for required in ("Gestionar", "Guardar nueva versión", "Cancelar publicación", "/replace", "window.confirm", "scheduled_for"):
            self.assertIn(required, ui)
        for forbidden in ("setInterval(", "MutationObserver(", "target_id:", "target_name:", "asset_id:", "render_id:", "media_url:", "link_url:"):
            self.assertNotIn(forbidden, ui)

    def test_loader_and_mac_build_chain_wave42_after_wave41(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("/inbox-replies.js", loader)
        self.assertIn("/editorial-management.js", loader)
        self.assertLess(loader.index("/inbox-replies.js"), loader.index("/editorial-management.js"))
        self.assertIn("service_wave41_app import serve", build)
        self.assertIn("service_wave42_app import serve", build)
        self.assertLess(build.index("service_wave41_app import serve"), build.index("service_wave42_app import serve"))
        self.assertIn("audit_wave42_editorial_management.sh", build)


if __name__ == "__main__":
    unittest.main()
