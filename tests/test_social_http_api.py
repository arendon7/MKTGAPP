import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def request_json(url, *, method="GET", payload=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    with urlopen(req, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class SocialHttpApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.project = self.runtime.create_project("Distribucion")
        self.project_id = self.project["id"]

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_meta_status_exposes_requirement_not_secret_and_scheduler_is_explicit(self):
        status, payload = request_json(f"{self.base}/api/meta/status")
        self.assertEqual(status, 200)
        self.assertIn("configured", payload)
        self.assertIn("scheduler", payload)
        self.assertNotIn("token", payload)
        self.assertNotIn("access_token", payload)
        self.assertNotIn("authorization", payload)
        if not payload["configured"]:
            self.assertIn("META_ACCESS_TOKEN", payload["missing"])

    def test_social_browser_bundle_is_really_served(self):
        with urlopen(f"{self.base}/social.js", timeout=5) as response:
            body = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)
            self.assertIn("Meta, publicaciones y pauta", body)
            self.assertIn("createMetaCampaign", body)

    def test_project_publication_create_queue_list_and_cancel(self):
        status, row = request_json(
            f"{self.base}/api/projects/{self.project_id}/publications",
            method="POST",
            payload={
                "channel": "facebook_page",
                "target_id": "page-1",
                "target_name": "Greenatics",
                "kind": "text",
                "message": "Transformar residuos en vida",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(row["status"], "DRAFT")
        publication_id = row["id"]

        status, queued = request_json(
            f"{self.base}/api/projects/{self.project_id}/publications/{publication_id}/queue",
            method="POST",
            payload={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(queued["status"], "QUEUED")
        self.assertIsNotNone(queued["scheduled_for"])

        status, rows = request_json(f"{self.base}/api/projects/{self.project_id}/publications")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in rows], [publication_id])

        status, detail = request_json(f"{self.base}/api/projects/{self.project_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["publications"][0]["id"], publication_id)

        status, cancelled = request_json(
            f"{self.base}/api/projects/{self.project_id}/publications/{publication_id}",
            method="DELETE",
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_http_rejects_secret_in_publication_payload(self):
        req = Request(
            f"{self.base}/api/projects/{self.project_id}/publications",
            data=json.dumps({
                "channel": "facebook_page",
                "target_id": "page-1",
                "kind": "text",
                "message": "No secret",
                "access_token": "must-never-persist",
            }).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(req, timeout=5)
        self.assertEqual(raised.exception.code, 400)
        body = json.loads(raised.exception.read().decode("utf-8"))
        self.assertIn("credentials must not be persisted", body["error"])

    def test_cross_project_publication_access_fails_closed(self):
        other = self.runtime.create_project("Otro")
        row = self.runtime.create_publication(self.project_id, {
            "channel": "facebook_page",
            "target_id": "page-1",
            "kind": "text",
            "message": "Scoped",
        })
        req = Request(
            f"{self.base}/api/projects/{other['id']}/publications/{row['id']}/queue",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(req, timeout=5)
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
