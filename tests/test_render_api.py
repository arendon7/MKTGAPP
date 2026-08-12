import hashlib
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.render_queue import RenderQueue
from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FAKE_FFMPEG = r'''#!__PYTHON__
import pathlib, sys, time
out = pathlib.Path(sys.argv[-1])
slow = 'slow' in out.name
steps = 50 if slow else 4
for i in range(steps):
    print(f"out_time_us={int(((i + 1) / steps) * 1_000_000)}", flush=True)
    time.sleep(0.025 if slow else 0.01)
out.write_bytes(b"api-rendered-video")
print("progress=end", flush=True)
'''


class RenderApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runtime = AppRuntime.create(ROOT, root / "data")
        self.runtime.renders.shutdown()
        self.ffmpeg = root / "fake-ffmpeg"
        self.ffmpeg.write_text(FAKE_FFMPEG.replace("__PYTHON__", sys.executable), encoding="utf-8")
        self.ffmpeg.chmod(0o755)
        self.runtime.renders = RenderQueue(
            self.runtime.data_root / "State" / "renders-api",
            self.runtime.projects,
            self.runtime.workspace,
            str(self.ffmpeg),
            video_codec="mpeg4",
        )
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def request(self, method: str, path: str, payload=None):
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(self.base + path, data=body, method=method, headers={"Content-Type": "application/json"})
        with urlopen(request, timeout=5) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None

    def upload(self, project_id: str, filename: str, body: bytes):
        request = Request(
            self.base + f"/api/projects/{project_id}/assets/upload?filename={filename}&kind=video",
            data=body,
            method="POST",
            headers={"Content-Type": "video/mp4"},
        )
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read())

    def wait_terminal(self, job_id: str, timeout: float = 4.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, job = self.request("GET", f"/api/renders/{job_id}")
            if job["status"] in {"PASS", "FAIL", "CANCELLED", "INTERRUPTED"}:
                return job
            time.sleep(0.03)
        self.fail(f"render {job_id} did not finish")

    def test_http_render_pass_download_and_traceability(self):
        _, project = self.request("POST", "/api/projects", {"name": "Render API"})
        asset = self.upload(project["id"], "source.mp4", b"source")
        status, job = self.request(
            "POST",
            f"/api/projects/{project['id']}/renders",
            {"asset_id": asset["id"], "start": 1.5, "end": 3.0, "aspect": "9:16", "label": "reel"},
        )
        self.assertEqual(status, 202)
        self.assertEqual((job["width"], job["height"]), (1080, 1920))
        done = self.wait_terminal(job["id"])
        self.assertEqual(done["status"], "PASS", done["error"])
        self.assertEqual(done["progress"], 1.0)
        self.assertEqual(done["sha256"], hashlib.sha256(b"api-rendered-video").hexdigest())
        self.assertTrue(done["artifact_ref"])

        with urlopen(self.base + f"/api/renders/{job['id']}/file", timeout=5) as response:
            downloaded = response.read()
            disposition = response.headers["Content-Disposition"]
        self.assertEqual(downloaded, b"api-rendered-video")
        self.assertIn(done["output_name"], disposition)

        _, project_detail = self.request("GET", f"/api/projects/{project['id']}")
        self.assertEqual(len(project_detail["renders"]), 1)
        _, timeline = self.request("GET", "/api/timeline")
        kinds = [row["kind"] for row in timeline]
        self.assertIn("render.queued", kinds)
        self.assertIn("render.completed", kinds)
        self.assertIn("artifact.recorded", kinds)

    def test_http_render_can_be_cancelled(self):
        _, project = self.request("POST", "/api/projects", {"name": "Cancel"})
        asset = self.upload(project["id"], "source.mp4", b"source")
        _, job = self.request(
            "POST",
            f"/api/projects/{project['id']}/renders",
            {"asset_id": asset["id"], "start": 0, "end": 4, "aspect": "16:9", "label": "slow"},
        )
        _, cancelling = self.request("POST", f"/api/renders/{job['id']}/cancel", {})
        self.assertIn(cancelling["status"], {"CANCELLING", "CANCELLED"})
        done = self.wait_terminal(job["id"])
        self.assertEqual(done["status"], "CANCELLED")
        self.assertFalse(self.runtime.renders.output_path(job["id"]).exists())

    def test_browser_ui_exposes_render_controls(self):
        with urlopen(self.base + "/", timeout=5) as response:
            html = response.read().decode("utf-8")
        with urlopen(self.base + "/app.js", timeout=5) as response:
            javascript = response.read().decode("utf-8")
        self.assertIn("Renders y exportaciones", html)
        self.assertIn("render-count", html)
        self.assertIn("startRender", javascript)
        self.assertIn("/renders", javascript)
        self.assertIn("Exportar", javascript)


if __name__ == "__main__":
    unittest.main()
