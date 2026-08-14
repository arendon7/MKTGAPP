import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from binario_marketing.service_wave34 import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def request_json(url, *, method="GET", payload=None, data=None, headers=None):
    request_headers = {"Accept": "application/json", **(headers or {})}
    body = data
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = Request(url, data=body, method=method, headers=request_headers)
    with urlopen(request, timeout=10) as response:
        raw = response.read()
        return response.status, json.loads(raw.decode("utf-8")) if raw else None


class CompanyMediaHttpTests(unittest.TestCase):
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

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def upload(self, name="reel.mp4", kind="video", body=b"fake-managed-video"):
        url = self.base + f"/api/companies/{self.company['id']}/media/upload?filename={quote(name)}&kind={quote(kind)}"
        return request_json(url, method="POST", data=body, headers={"Content-Type": "application/octet-stream"})

    def test_upload_list_stream_and_delete(self):
        status, media = self.upload()
        self.assertEqual(status, 201)
        _, rows = request_json(self.base + f"/api/companies/{self.company['id']}/media")
        self.assertEqual([row["id"] for row in rows], [media["id"]])
        with urlopen(self.base + f"/api/companies/{self.company['id']}/media/{media['id']}/file", timeout=10) as response:
            self.assertEqual(response.read(), b"fake-managed-video")
        status, removed = request_json(
            self.base + f"/api/companies/{self.company['id']}/media/{media['id']}",
            method="DELETE",
        )
        self.assertEqual(status, 200)
        self.assertEqual(removed["id"], media["id"])

    def test_local_reel_intent_uses_company_media_not_fake_project(self):
        _, media = self.upload()
        self.runtime.company_media.update_probe(
            self.company["id"], media["id"], width=1080, height=1920, duration=10.0
        )
        status, publication = request_json(
            self.base + f"/api/companies/{self.company['id']}/publications",
            method="POST",
            payload={
                "channel": "facebook_page",
                "kind": "reel",
                "message": "Reel desde biblioteca",
                "asset_id": media["id"],
                "scheduled_for": "2030-01-02T12:00:00+00:00",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(publication["project_id"], self.company["id"])
        self.assertEqual(publication["asset_id"], media["id"])
        self.assertIsNone(publication["render_id"])
        self.assertIsNone(publication["media_url"])
        self.assertEqual(publication["status"], "QUEUED")
        self.assertEqual(self.runtime.projects.list_projects(), [])

    def test_instagram_local_reel_intent_uses_same_managed_asset_contract(self):
        _, media = self.upload(name="portrait.mov")
        self.runtime.company_media.update_probe(
            self.company["id"], media["id"], width=1080, height=1920, duration=8.0
        )
        _, publication = request_json(
            self.base + f"/api/companies/{self.company['id']}/publications",
            method="POST",
            payload={
                "channel": "instagram",
                "kind": "reel",
                "message": "Instagram local",
                "asset_id": media["id"],
                "scheduled_for": "2030-01-02T12:00:00+00:00",
            },
        )
        self.assertEqual(publication["asset_id"], media["id"])
        self.assertIsNone(publication["render_id"])
        self.assertEqual(publication["target_id"], "ig-1")

    def test_referenced_media_cannot_be_deleted(self):
        _, media = self.upload()
        self.runtime.company_media.update_probe(
            self.company["id"], media["id"], width=1080, height=1920, duration=10.0
        )
        request_json(
            self.base + f"/api/companies/{self.company['id']}/publications",
            method="POST",
            payload={
                "channel": "facebook_page",
                "kind": "reel",
                "message": "Programado",
                "asset_id": media["id"],
                "scheduled_for": "2030-01-02T12:00:00+00:00",
            },
        )
        request = Request(
            self.base + f"/api/companies/{self.company['id']}/media/{media['id']}", method="DELETE"
        )
        from urllib.error import HTTPError
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=10)
        self.assertEqual(raised.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
