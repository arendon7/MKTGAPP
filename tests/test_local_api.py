import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class LocalApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "data"
        self.runtime = AppRuntime.create(ROOT, self.data_root)
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.tmp.cleanup()

    def request(self, method, path, payload=None):
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        req = Request(self.base + path, data=data, method=method, headers={"Content-Type": "application/json"})
        with urlopen(req, timeout=5) as response:
            body = response.read()
            return response.status, json.loads(body) if body else None

    def test_health_static_and_12_app_inventory(self):
        status, health = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(health["status"], "ok")
        status, apps = self.request("GET", "/api/apps")
        self.assertEqual(status, 200)
        self.assertEqual(len(apps), 12)
        with urlopen(self.base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        self.assertIn("Marketing Workspace", html)

    def test_project_asset_editor_handoff_vertical_flow(self):
        status, project = self.request("POST", "/api/projects", {"name": "Campaña Café"})
        self.assertEqual(status, 201)
        project_id = project["id"]
        source = Path(self.tmp.name) / "source.mp4"
        source.write_bytes(b"video")
        status, asset = self.request("POST", f"/api/projects/{project_id}/assets", {"source_path": str(source), "kind": "video"})
        self.assertEqual(status, 201)
        self.assertTrue(asset["artifact_ref"])

        status, editor = self.request("POST", f"/api/projects/{project_id}/editor/actions", {"action": "add_clip", "asset_id": asset["id"], "start": 0, "end": 30, "track": 0})
        self.assertEqual(status, 200)
        self.assertEqual(len(editor["clips"]), 1)

        with self.assertRaises(HTTPError) as blocked:
            self.request("DELETE", f"/api/projects/{project_id}/assets/{asset['id']}")
        self.assertEqual(blocked.exception.code, 409)

        clip_id = editor["clips"][0]["id"]
        _, editor = self.request("POST", f"/api/projects/{project_id}/editor/actions", {"action": "split", "clip_id": clip_id, "at": 12})
        self.assertEqual(len(editor["clips"]), 2)
        for clip in list(editor["clips"]):
            _, editor = self.request("POST", f"/api/projects/{project_id}/editor/actions", {"action": "delete_clip", "clip_id": clip["id"]})
        self.assertEqual(editor["clips"], [])
        status, deleted = self.request("DELETE", f"/api/projects/{project_id}/assets/{asset['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(deleted["deleted"])

        status, handoff = self.request("POST", f"/api/projects/{project_id}/handoffs", {"to_app": "09-propuestas-ia", "summary": "Continuar con propuesta"})
        self.assertEqual(status, 201)
        self.assertEqual(handoff["to_app"], "09-propuestas-ia")
        _, detail = self.request("GET", f"/api/projects/{project_id}")
        self.assertEqual(len(detail["handoffs"]), 1)
        _, timeline = self.request("GET", "/api/timeline")
        kinds = [event["kind"] for event in timeline]
        self.assertIn("project.created", kinds)
        self.assertIn("workspace.handoff", kinds)
        self.assertIn("editor.action", kinds)

    def test_clipper_endpoint_returns_requested_non_overlapping_candidates(self):
        segments = [
            {"start": 0, "end": 8, "text": "¿Cómo evitar este error?"},
            {"start": 8, "end": 19, "text": "La clave es definir el objetivo."},
            {"start": 19, "end": 31, "text": "Después mide el resultado."},
            {"start": 31, "end": 43, "text": "Nunca publiques sin revisar."},
            {"start": 43, "end": 56, "text": "Porque una pieza clara convierte mejor."},
            {"start": 56, "end": 70, "text": "Cierra con una idea concreta."},
        ]
        status, clips = self.request("POST", "/api/clipper/select", {"segments": segments, "target_count": 2, "min_duration": 15, "max_duration": 30})
        self.assertEqual(status, 200)
        self.assertEqual(len(clips), 2)
        self.assertLessEqual(clips[0]["end"], clips[1]["start"])


if __name__ == "__main__":
    unittest.main()
