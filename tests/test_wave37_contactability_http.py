import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave37 import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def request_json(url, *, method="GET", payload=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method, headers=headers)
    with urlopen(request, timeout=10) as response:
        raw = response.read()
        return response.status, json.loads(raw.decode("utf-8")) if raw else None


class ContactabilityHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        _, self.company = request_json(self.base + "/api/companies", method="POST", payload={"name": "Greenatics"})
        _, self.contact = request_json(
            self.base + f"/api/companies/{self.company['id']}/contacts",
            method="POST",
            payload={"name": "Ana", "email": "ana@example.com", "whatsapp": "+573001112233"},
        )

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def contactability_url(self, channel=None):
        base = self.base + f"/api/companies/{self.company['id']}/contacts/{self.contact['id']}/contactability"
        return f"{base}/{channel}" if channel else base

    def test_default_unknown_then_opt_in_and_reset(self):
        _, payload = request_json(self.contactability_url())
        self.assertEqual(payload["channels"]["email"]["status"], "UNKNOWN")
        self.assertFalse(payload["channels"]["email"]["eligible"])
        self.assertTrue(payload["channels"]["email"]["has_destination"])
        _, email = request_json(
            self.contactability_url("email"),
            method="PATCH",
            payload={
                "status": "OPTED_IN",
                "source": "Formulario web",
                "captured_at": "2030-01-02T12:00:00+00:00",
                "note": "Consentimiento registrado",
            },
        )
        self.assertEqual(email["status"], "OPTED_IN")
        self.assertTrue(email["eligible"])
        _, reset = request_json(self.contactability_url("email"), method="DELETE")
        self.assertEqual(reset["status"], "UNKNOWN")
        self.assertFalse(reset["eligible"])

    def test_cross_company_contactability_is_not_exposed(self):
        _, other = request_json(self.base + "/api/companies", method="POST", payload={"name": "Sistema Binario"})
        request = Request(
            self.base + f"/api/companies/{other['id']}/contacts/{self.contact['id']}/contactability",
            headers={"Accept": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(raised.exception.code, 404)

    def test_campaign_snapshot_is_stable_but_current_eligibility_changes(self):
        _, campaign = request_json(
            self.base + f"/api/companies/{self.company['id']}/campaigns",
            method="POST",
            payload={
                "name": "Campaña consentimiento",
                "objective": "LEADS",
                "channels": ["email", "whatsapp"],
                "audience_contact_ids": [self.contact["id"]],
            },
        )
        self.assertEqual(campaign["audience_contact_ids"], [self.contact["id"]])
        self.assertEqual(campaign["readiness"]["email"]["unknown"], 1)
        self.assertEqual(campaign["readiness"]["email"]["eligible"], 0)
        self.assertEqual(campaign["readiness"]["email"]["send_gate"], "OPTED_IN_REQUIRED")

        request_json(
            self.contactability_url("email"),
            method="PATCH",
            payload={"status": "OPTED_IN", "source": "Landing", "captured_at": "2030-01-01T00:00:00+00:00"},
        )
        request_json(
            self.contactability_url("whatsapp"),
            method="PATCH",
            payload={"status": "OPTED_IN", "source": "Evento", "captured_at": "2030-01-01T00:00:00+00:00"},
        )
        _, detail = request_json(
            self.base + f"/api/companies/{self.company['id']}/campaigns/{campaign['id']}"
        )
        self.assertEqual(detail["campaign"]["audience_contact_ids"], [self.contact["id"]])
        self.assertEqual(detail["campaign"]["readiness"]["email"]["eligible"], 1)
        self.assertEqual(detail["campaign"]["readiness"]["whatsapp"]["eligible"], 1)

        request_json(
            self.contactability_url("whatsapp"),
            method="PATCH",
            payload={
                "status": "OPTED_OUT",
                "source": "Solicitud del contacto",
                "captured_at": "2030-02-01T00:00:00+00:00",
            },
        )
        _, detail = request_json(
            self.base + f"/api/companies/{self.company['id']}/campaigns/{campaign['id']}"
        )
        ready = detail["campaign"]["readiness"]["whatsapp"]
        self.assertEqual(ready["eligible"], 0)
        self.assertEqual(ready["opted_out"], 1)
        self.assertEqual(ready["suppressed"], 1)
        self.assertEqual(detail["campaign"]["audience_contact_ids"], [self.contact["id"]])
        self.assertEqual(self.runtime.social.list(self.company["id"]), [])

    def test_audience_payload_reports_current_contactability(self):
        _, audience = request_json(
            self.base + f"/api/companies/{self.company['id']}/audiences",
            method="POST",
            payload={"name": "Leads", "contact_ids": [self.contact["id"]]},
        )
        self.assertEqual(audience["contactability"]["email"]["unknown"], 1)
        request_json(
            self.contactability_url("email"),
            method="PATCH",
            payload={"status": "OPTED_IN", "source": "CRM", "captured_at": "2030-01-01T00:00:00+00:00"},
        )
        _, audience = request_json(
            self.base + f"/api/companies/{self.company['id']}/audiences/{audience['id']}"
        )
        self.assertEqual(audience["contactability"]["email"]["eligible"], 1)
        _, summary = request_json(self.base + f"/api/contactability/summary?company_id={self.company['id']}")
        self.assertEqual(summary["channels"]["email"]["eligible"], 1)
        self.assertEqual(summary["channels"]["whatsapp"]["unknown"], 1)


if __name__ == "__main__":
    unittest.main()
