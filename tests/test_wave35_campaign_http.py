import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave35 import AppRuntime, create_server


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


class CampaignHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        _, self.company = request_json(self.base + "/api/companies", method="POST", payload={"name": "Greenatics"})
        request_json(
            self.base + f"/api/companies/{self.company['id']}",
            method="PATCH",
            payload={
                "facebook_page_id": "page-1",
                "facebook_page_name": "Greenatics",
                "instagram_id": "ig-1",
                "instagram_username": "greenatics",
            },
        )
        _, self.contact = request_json(
            self.base + f"/api/companies/{self.company['id']}/contacts",
            method="POST",
            payload={"name": "Cliente Uno", "email": "cliente@example.com", "whatsapp": "+573001112233"},
        )
        self.media = self.runtime.company_media.add_uploaded(
            self.company["id"], "pieza.png", "image", io.BytesIO(b"campaign-image"), len(b"campaign-image")
        )
        _, self.publication = request_json(
            self.base + f"/api/companies/{self.company['id']}/publications",
            method="POST",
            payload={
                "channel": "facebook_page",
                "kind": "text",
                "message": "Copy campaña",
                "scheduled_for": "2030-01-10T12:00:00+00:00",
            },
        )

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_campaign_links_crm_content_publication_and_never_executes_channels(self):
        status, campaign = request_json(
            self.base + f"/api/companies/{self.company['id']}/campaigns",
            method="POST",
            payload={
                "name": "Campaña Q1",
                "objective": "LEADS",
                "channels": ["facebook_page", "instagram", "email", "whatsapp"],
                "audience_contact_ids": [self.contact["id"]],
                "media_ids": [self.media.id],
                "publication_ids": [self.publication["id"]],
                "start_at": "2030-01-01T08:00:00+00:00",
                "end_at": "2030-01-31T18:00:00+00:00",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(campaign["status"], "PLANNING")
        self.assertTrue(campaign["readiness"]["facebook_page"]["provider_configured"])
        self.assertTrue(campaign["readiness"]["instagram"]["provider_configured"])
        self.assertFalse(campaign["readiness"]["email"]["provider_configured"])
        self.assertTrue(campaign["readiness"]["email"]["planned_only"])
        self.assertEqual(campaign["readiness"]["email"]["audience_reachable"], 1)
        self.assertFalse(campaign["readiness"]["whatsapp"]["provider_configured"])
        self.assertEqual(self.runtime.social.get(self.publication["id"]).status, "QUEUED")

        _, detail = request_json(
            self.base + f"/api/companies/{self.company['id']}/campaigns/{campaign['id']}"
        )
        self.assertEqual(detail["audience"][0]["id"], self.contact["id"])
        self.assertEqual(detail["media"][0]["id"], self.media.id)
        self.assertEqual(detail["publications"][0]["id"], self.publication["id"])

        _, updated = request_json(
            self.base + f"/api/companies/{self.company['id']}/campaigns/{campaign['id']}",
            method="PATCH",
            payload={"status": "IN_PROGRESS", "notes": "Ejecución manual coordinada"},
        )
        self.assertEqual(updated["status"], "IN_PROGRESS")
        self.assertEqual(self.runtime.social.get(self.publication["id"]).status, "QUEUED")

        _, summary = request_json(self.base + f"/api/campaigns/summary?company_id={self.company['id']}")
        self.assertEqual(summary["in_progress"], 1)
        _, dashboard = request_json(self.base + f"/api/ops/dashboard?company_id={self.company['id']}")
        self.assertEqual(dashboard["campaigns"]["in_progress"], 1)

    def test_cross_company_contact_media_and_publication_refs_are_rejected(self):
        _, other = request_json(self.base + "/api/companies", method="POST", payload={"name": "Sistema Binario"})
        _, other_contact = request_json(
            self.base + f"/api/companies/{other['id']}/contacts",
            method="POST",
            payload={"name": "Privado"},
        )
        other_media = self.runtime.company_media.add_uploaded(
            other["id"], "private.png", "image", io.BytesIO(b"private"), len(b"private")
        )
        other_publication = self.runtime.social.create(other["id"], {
            "channel": "facebook_page",
            "target_id": "other-page",
            "kind": "text",
            "message": "Other",
        })
        for field, value in (
            ("audience_contact_ids", [other_contact["id"]]),
            ("media_ids", [other_media.id]),
            ("publication_ids", [other_publication.id]),
        ):
            request = Request(
                self.base + f"/api/companies/{self.company['id']}/campaigns",
                data=json.dumps({"name": "Cross", field: value}).encode("utf-8"),
                method="POST",
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=10)
            self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
