import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave36 import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def request_json(url, *, method="GET", payload=None, data=None, headers=None):
    body = data
    request_headers = {"Accept": "application/json", **(headers or {})}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, method=method, headers=request_headers)
    with urlopen(request, timeout=10) as response:
        raw = response.read()
        return response.status, json.loads(raw.decode("utf-8")) if raw else None


class AudienceHttpTests(unittest.TestCase):
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

    def import_csv(self, content, strategy="skip"):
        return request_json(
            self.base + f"/api/companies/{self.company['id']}/contacts/import?strategy={strategy}",
            method="POST",
            data=content,
            headers={"Content-Type": "text/csv; charset=utf-8"},
        )

    def test_import_then_create_update_delete_audience(self):
        status, report = self.import_csv(
            "nombre,correo,whatsapp,etiquetas\nAna,ana@example.com,+573001112233,cliente\nLuis,luis@example.com,,lead\n".encode("utf-8")
        )
        self.assertEqual(status, 200)
        self.assertEqual(report["created"], 2)
        self.assertEqual(report["error_count"], 0)
        contacts = self.runtime.crm.list_contacts(self.company["id"])
        status, audience = request_json(
            self.base + f"/api/companies/{self.company['id']}/audiences",
            method="POST",
            payload={"name": "Clientes lanzamiento", "description": "Snapshot", "contact_ids": [row.id for row in contacts]},
        )
        self.assertEqual(status, 201)
        self.assertEqual(audience["member_count"], 2)
        self.assertEqual(audience["email_reachable"], 2)
        self.assertEqual(audience["whatsapp_reachable"], 1)
        _, listed = request_json(self.base + f"/api/companies/{self.company['id']}/audiences")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], audience["id"])
        _, updated = request_json(
            self.base + f"/api/companies/{self.company['id']}/audiences/{audience['id']}",
            method="PATCH",
            payload={"contact_ids": [contacts[0].id]},
        )
        self.assertEqual(updated["member_count"], 1)
        _, summary = request_json(self.base + f"/api/audiences/summary?company_id={self.company['id']}")
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["unique_contacts"], 1)
        _, dashboard = request_json(self.base + f"/api/ops/dashboard?company_id={self.company['id']}")
        self.assertEqual(dashboard["audiences"]["total"], 1)
        status, removed = request_json(
            self.base + f"/api/companies/{self.company['id']}/audiences/{audience['id']}", method="DELETE"
        )
        self.assertEqual(status, 200)
        self.assertEqual(removed["id"], audience["id"])

    def test_update_strategy_is_explicit_and_cross_company_members_are_blocked(self):
        self.import_csv(b"name,email,organization\nAna,ana@example.com,Original\n")
        _, report = self.import_csv(b"name,email,organization\nAna Nueva,ANA@example.com,Nueva\n", strategy="update")
        self.assertEqual(report["updated"], 1)
        contact = self.runtime.crm.list_contacts(self.company["id"])[0]
        self.assertEqual(contact.name, "Ana Nueva")
        self.assertEqual(contact.organization, "Nueva")

        _, other = request_json(self.base + "/api/companies", method="POST", payload={"name": "Sistema Binario"})
        _, foreign = request_json(
            self.base + f"/api/companies/{other['id']}/contacts", method="POST", payload={"name": "Privado"}
        )
        request = Request(
            self.base + f"/api/companies/{self.company['id']}/audiences",
            data=json.dumps({"name": "Cross", "contact_ids": [foreign["id"]]}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(raised.exception.code, 404)

    def test_csv_import_never_creates_campaigns_publications_or_external_actions(self):
        _, report = self.import_csv(b"name,email\nAna,ana@example.com\n")
        self.assertEqual(report["created"], 1)
        self.assertEqual(self.runtime.campaigns.list(self.company["id"]), [])
        self.assertEqual(self.runtime.social.list(self.company["id"]), [])
        self.assertEqual(self.runtime.audiences.list(self.company["id"]), [])


if __name__ == "__main__":
    unittest.main()
