import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave31 import AppRuntime, create_server


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


class Wave31HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_company_create_configure_publish_intent_and_calendar(self):
        status, company = request_json(self.base + "/api/companies", method="POST", payload={"name": "Greenatics"})
        self.assertEqual(status, 201)
        company_id = company["id"]
        status, configured = request_json(
            self.base + f"/api/companies/{company_id}",
            method="PATCH",
            payload={"facebook_page_id": "page-1", "facebook_page_name": "Greenatics"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(configured["facebook_page_id"], "page-1")

        status, publication = request_json(
            self.base + f"/api/companies/{company_id}/publications",
            method="POST",
            payload={
                "channel": "facebook_page",
                "kind": "text",
                "message": "Publicación central",
                "scheduled_for": "2030-01-02T12:00:00+00:00",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(publication["project_id"], company_id)
        self.assertEqual(publication["status"], "QUEUED")

        _, calendar = request_json(self.base + f"/api/ops/calendar?company_id={company_id}")
        self.assertEqual(len(calendar), 1)
        self.assertEqual(calendar[0]["company_name"], "Greenatics")
        _, dashboard = request_json(self.base + f"/api/ops/dashboard?company_id={company_id}")
        self.assertEqual(dashboard["summary"]["queued"], 1)

    def test_wave31_static_bundles_are_served(self):
        with urlopen(self.base + "/marketing-ops.js", timeout=5) as response:
            js = response.read().decode("utf-8")
        with urlopen(self.base + "/marketing-ops.css", timeout=5) as response:
            css = response.read().decode("utf-8")
        self.assertIn("Centro de operaciones", js)
        self.assertIn("Calendario", js)
        self.assertIn("Publicar", js)
        self.assertIn("CRM", js)
        self.assertIn("Contenido", js)
        self.assertIn("marketing-ops-shell", css)


class Wave31UiContractTests(unittest.TestCase):
    def test_operations_is_default_and_video_is_secondary_content_tool(self):
        js = (ROOT / "web" / "marketing-ops.js").read_text(encoding="utf-8")
        loader = (ROOT / "web" / "instagram-local-reel.js").read_text(encoding="utf-8")
        for required in (
            "Centro de operaciones",
            "Todas las empresas",
            "+ Programar publicación",
            "Calendario editorial",
            "Empresas y cuentas",
            "Contenido → Video Studio",
            "marketingOpsState.view='home'",
            "opsShowLegacy",
        ):
            self.assertIn(required, js)
        self.assertIn("script.src='/marketing-ops.js'", loader)
        self.assertNotIn("setInterval(()=>submitOpsPublication", js)
        self.assertNotIn("MutationObserver(()=>submitOpsPublication", js)

    def test_company_composer_uses_company_api_not_project_creation(self):
        js = (ROOT / "web" / "marketing-ops.js").read_text(encoding="utf-8")
        self.assertIn("/api/companies/${encodeURIComponent(company.id)}/publications", js)
        self.assertNotIn("/api/projects',{method:'POST'", js)
        self.assertIn("El publicador principal no te obliga a pasar por el editor", js)

    def test_full_mac_launch_preserves_wave31_or_a_certified_extension(self):
        script = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertTrue(
            "from binario_marketing.service_wave31 import serve" in script
            or "from binario_marketing.service_wave32 import serve" in script
            or "from binario_marketing.service_wave34 import serve" in script
            or "from binario_marketing.service_wave35 import serve" in script
        )
        self.assertNotIn("from binario_marketing.service_wave27 import serve", script)


if __name__ == "__main__":
    unittest.main()