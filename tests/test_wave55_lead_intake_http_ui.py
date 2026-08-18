import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave55_guard_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave55LeadIntakeHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
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

    def request_json(self, path, *, method="GET", body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(self.base + path, method=method, data=data, headers={"Content-Type": "application/json"} if data else {})
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_bundle_and_local_intake_contract_are_served(self):
        with urlopen(self.base + "/lead-intake.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        self.assertIn("Lead Intake & Conversion", ui)
        self.assertIn("Registrar lead sin tocar CRM", ui)
        self.assertIn("Exact identity · no fuzzy", ui)
        status, payload = self.request_json(f"/api/companies/{self.company['id']}/lead-intake")
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema"], "binario.marketing.lead-intake-center.v1")
        self.assertFalse(payload["ingress_contract"]["public_desktop_webhook"])
        self.assertFalse(payload["matching_contract"]["name_fuzzy_matching"])
        self.assertFalse(payload["conversion_contract"]["intake_mutates_crm"])

    def test_http_intake_then_explicit_conversion_roundtrip(self):
        status, lead = self.request_json(
            f"/api/companies/{self.company['id']}/lead-intake",
            method="POST",
            body={"connector": "API_IMPORT", "source_ref": "external_1", "name": "Lead", "email": "lead@example.com"},
        )
        self.assertEqual(status, 201)
        self.assertEqual(lead["status"], "NEW")
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)
        status, converted = self.request_json(
            f"/api/companies/{self.company['id']}/lead-intake/{lead['id']}/convert",
            method="POST",
            body={"action": "CREATE_CONTACT"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(converted["status"], "CONVERTED")
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 1)

    def test_csv_http_intake_never_creates_contacts(self):
        content = b"name,email\nAna,ana@example.com\nBeto,beto@example.com\n"
        request = Request(
            self.base + f"/api/companies/{self.company['id']}/lead-intake/csv",
            method="POST",
            data=content,
            headers={"Content-Type": "text/csv"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 201)
        self.assertEqual(payload["created"], 2)
        self.assertEqual(payload["crm_mutations"], 0)
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)

    def test_loader_builder_and_ui_preserve_no_polling_no_public_webhook_boundary(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_wave55_lead_intake.sh").read_text(encoding="utf-8")
        ui = (ROOT / "web" / "lead-intake.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave55_app.py").read_text(encoding="utf-8")
        guard = (ROOT / "src" / "binario_marketing" / "service_wave55_guard_app.py").read_text(encoding="utf-8")
        self.assertIn("capture.addEventListener('load',loadLeadIntake", loader)
        self.assertIn("lead.src='/lead-intake.js'", loader)
        self.assertIn("service_wave54_app','service_wave55_app','service_wave55_guard_app", builder)
        self.assertIn("audit_wave55_lead_intake.sh", builder)
        self.assertIn("Wave 52", builder)
        self.assertIn("Wave 53", builder)
        self.assertIn("Wave 54", builder)
        self.assertIn("Wave 55", builder)
        self.assertIn("_lead_attribution_prepared", guard)
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertIn('"public_desktop_webhook": False', service)
        self.assertIn('"automatic_crm_conversion": False', service)
        self.assertNotIn(".github/workflows", audit)


if __name__ == "__main__":
    unittest.main()
