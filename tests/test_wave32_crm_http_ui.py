import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave32 import AppRuntime, create_server


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


class CRMHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        _, self.company = request_json(self.base + "/api/companies", method="POST", payload={"name": "Greenatics"})

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_end_to_end_contact_pipeline_and_followup(self):
        company_id = self.company["id"]
        status, contact = request_json(
            self.base + f"/api/companies/{company_id}/contacts",
            method="POST",
            payload={"name": "Carlos Pérez", "organization": "Finca Café", "whatsapp": "+573001112233"},
        )
        self.assertEqual(status, 201)
        status, opportunity = request_json(
            self.base + f"/api/companies/{company_id}/opportunities",
            method="POST",
            payload={"contact_id": contact["id"], "title": "Pedido fertilizante", "value": 1800000, "currency": "COP"},
        )
        self.assertEqual(status, 201)
        _, opportunity = request_json(
            self.base + f"/api/companies/{company_id}/opportunities/{opportunity['id']}",
            method="PATCH",
            payload={"stage": "PROPOSAL", "next_action": "Confirmar decisión"},
        )
        self.assertEqual(opportunity["stage"], "PROPOSAL")
        status, activity = request_json(
            self.base + f"/api/companies/{company_id}/activities",
            method="POST",
            payload={"contact_id": contact["id"], "opportunity_id": opportunity["id"], "kind": "CALL", "summary": "Llamar al cliente"},
        )
        self.assertEqual(status, 201)
        _, detail = request_json(self.base + f"/api/companies/{company_id}/contacts/{contact['id']}")
        self.assertEqual(len(detail["opportunities"]), 1)
        self.assertEqual(len(detail["activities"]), 1)
        _, completed = request_json(
            self.base + f"/api/companies/{company_id}/activities/{activity['id']}/complete",
            method="POST",
            payload={},
        )
        self.assertIsNotNone(completed["completed_at"])
        _, summary = request_json(self.base + f"/api/crm/summary?company_id={company_id}")
        self.assertEqual(summary["contacts"], 1)
        self.assertEqual(summary["opportunities_open"], 1)
        self.assertEqual(summary["pending_activities"], 0)
        _, dashboard = request_json(self.base + f"/api/ops/dashboard?company_id={company_id}")
        self.assertEqual(dashboard["crm"]["contacts"], 1)

    def test_cross_company_contact_detail_is_not_exposed(self):
        company_id = self.company["id"]
        _, other = request_json(self.base + "/api/companies", method="POST", payload={"name": "Sistema Binario"})
        _, contact = request_json(self.base + f"/api/companies/{company_id}/contacts", method="POST", payload={"name": "Privado"})
        request = Request(self.base + f"/api/companies/{other['id']}/contacts/{contact['id']}", headers={"Accept": "application/json"})
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 404)

    def test_crm_bundle_is_served(self):
        with urlopen(self.base + "/crm.js", timeout=5) as response:
            js = response.read().decode("utf-8")
        self.assertIn("Contactos", js)
        self.assertIn("Pipeline", js)
        self.assertIn("Seguimientos", js)
        self.assertIn("no envía mensajes automáticamente", js)


class CRMUiContractTests(unittest.TestCase):
    def test_crm_is_real_not_placeholder_and_has_three_operational_surfaces(self):
        crm = (ROOT / "web" / "crm.js").read_text(encoding="utf-8")
        loader = (ROOT / "web" / "instagram-local-reel.js").read_text(encoding="utf-8")
        marketing = (ROOT / "web" / "marketing-ops.js").read_text(encoding="utf-8")
        for required in (
            "Contactos",
            "Pipeline",
            "Seguimientos",
            "FICHA DEL CONTACTO",
            "Nueva oportunidad",
            "SEGUIMIENTOS VENCIDOS",
            "/contacts",
            "/opportunities",
            "/activities",
        ):
            self.assertIn(required, crm)
        self.assertIn("crm.src='/crm.js'", loader)
        self.assertIn("data-ops-view=\"crm\"", marketing)
        self.assertNotIn("fetch('https://", crm)
        self.assertNotIn("window.open(", crm)

    def test_crm_never_auto_sends_external_messages(self):
        crm = (ROOT / "web" / "crm.js").read_text(encoding="utf-8")
        self.assertIn("no envía mensajes automáticamente", crm)
        for forbidden in (
            "sendWhatsApp(",
            "sendEmail(",
            "setInterval(()=>submit",
            "MutationObserver(()=>submit",
            "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, crm)

    def test_full_mac_launches_wave32_or_certified_extension(self):
        build = (ROOT / "scripts" / "build_full_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertTrue(
            "from binario_marketing.service_wave32 import serve" in build
            or "from binario_marketing.service_wave34 import serve" in build
            or "from binario_marketing.service_wave35 import serve" in build
            or "from binario_marketing.service_wave36 import serve" in build
            or "from binario_marketing.service_wave37_app import serve" in build
        )
        self.assertTrue(
            "from binario_marketing.service_wave32 import AppRuntime" in audit
            or "from binario_marketing.service_wave34 import AppRuntime" in audit
            or "from binario_marketing.service_wave35 import AppRuntime" in audit
            or "from binario_marketing.service_wave36 import AppRuntime" in audit
            or "from binario_marketing.service_wave37_app import AppRuntime" in audit
        )
        self.assertIn("crm.js", audit)
        self.assertIn("crm_store.py", audit)


if __name__ == "__main__":
    unittest.main()