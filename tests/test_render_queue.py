import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from binario_marketing.projects import ProjectStore
from binario_marketing.render_queue import RenderQueue, RenderRecord
from binario_marketing.workspace import Workspace


FAKE_FFMPEG = r'''#!__PYTHON__
import pathlib, sys, time
out = pathlib.Path(sys.argv[-1])
slow = 'slow' in out.name
steps = 40 if slow else 3
for i in range(steps):
    value = int(((i + 1) / steps) * 1_000_000)
    print(f"out_time_us={value}", flush=True)
    time.sleep(0.03 if slow else 0.01)
out.write_bytes(b"rendered-video")
print("progress=end", flush=True)
'''


class RenderQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.projects = ProjectStore(self.root / "projects")
        self.workspace = Workspace(self.root / "workspace")
        self.project = self.projects.create("Video")
        source = self.root / "source.mp4"
        source.write_bytes(b"source")
        self.asset = self.projects.add_asset(self.project.id, source, "video")
        self.ffmpeg = self.root / "fake-ffmpeg"
        self.ffmpeg.write_text(FAKE_FFMPEG.replace("__PYTHON__", sys.executable), encoding="utf-8")
        self.ffmpeg.chmod(0o755)
        self.queue = RenderQueue(self.root / "renders", self.projects, self.workspace, str(self.ffmpeg), video_codec="mpeg4")

    def tearDown(self):
        self.queue.shutdown()
        self.tmp.cleanup()

    def wait_terminal(self, job_id: str, timeout: float = 4.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            row = self.queue.get(job_id)
            if row.status in {"PASS", "FAIL", "CANCELLED", "INTERRUPTED"}:
                return row
            time.sleep(0.02)
        self.fail(f"render {job_id} did not reach terminal state")

    def test_render_completes_in_managed_exports_with_hash_and_artifact(self):
        row = self.queue.start(self.project.id, self.asset.id, 0, 1, 320, 180, "social clip")
        done = self.wait_terminal(row.id)
        self.assertEqual(done.status, "PASS", done.error)
        output = self.queue.output_path(done.id)
        self.assertEqual(output.parent, self.projects.exports_dir(self.project.id).resolve())
        self.assertEqual(done.bytes, len(b"rendered-video"))
        self.assertEqual(done.sha256, hashlib.sha256(b"rendered-video").hexdigest())
        self.assertTrue(done.artifact_ref)
        self.assertTrue(self.workspace.registries.verify_all())
        kinds = [entry.kind for entry in self.workspace.registries.timeline.entries()]
        self.assertIn("render.queued", kinds)
        self.assertIn("render.completed", kinds)
        self.assertIn("artifact.recorded", kinds)

    def test_cancel_removes_partial_output_and_records_terminal_state(self):
        row = self.queue.start(self.project.id, self.asset.id, 0, 2, 320, 180, "slow")
        deadline = time.time() + 2
        while time.time() < deadline and self.queue.get(row.id).status != "RUNNING":
            time.sleep(0.01)
        self.queue.cancel(row.id)
        done = self.wait_terminal(row.id)
        self.assertEqual(done.status, "CANCELLED")
        self.assertFalse(self.queue.output_path(row.id).exists())

    def test_immediate_cancel_is_safe_before_process_registration(self):
        row = self.queue.start(self.project.id, self.asset.id, 0, 2, 320, 180, "slow-immediate")
        self.queue.cancel(row.id)
        done = self.wait_terminal(row.id)
        self.assertEqual(done.status, "CANCELLED")
        self.assertFalse(self.queue.output_path(row.id).exists())

    def test_missing_ffmpeg_fails_job_without_breaking_queue_startup(self):
        queue = RenderQueue(self.root / "renders-missing", self.projects, self.workspace, str(self.root / "missing-ffmpeg"), video_codec="mpeg4")
        row = queue.start(self.project.id, self.asset.id, 0, 1, 320, 180)
        self.assertEqual(row.status, "FAIL")
        self.assertIn("FileNotFoundError", row.error)
        self.assertEqual(queue.list()[0].status, "FAIL")
        queue.shutdown()

    def test_restart_marks_active_jobs_interrupted_and_removes_partial(self):
        queue_root = self.root / "interrupted"
        queue_root.mkdir()
        output = self.projects.export_path(self.project.id, "job-partial.mp4")
        output.write_bytes(b"partial")
        record = RenderRecord(
            id="job", project_id=self.project.id, asset_id=self.asset.id,
            output_name=output.name, output_relative_path=f"exports/{output.name}",
            start=0, end=1, width=320, height=180, status="RUNNING", progress=0.5,
            created_at="2026-01-01T00:00:00+00:00", updated_at="2026-01-01T00:00:01+00:00",
        )
        (queue_root / "jobs.json").write_text(json.dumps([record.__dict__]), encoding="utf-8")
        recovered = RenderQueue(queue_root, self.projects, self.workspace, str(self.ffmpeg), video_codec="mpeg4")
        self.assertEqual(recovered.get("job").status, "INTERRUPTED")
        self.assertFalse(output.exists())
        recovered.shutdown()

    def test_progress_parser_supports_ffmpeg_time_fields(self):
        self.assertAlmostEqual(RenderQueue._progress_seconds("out_time_us=1250000"), 1.25)
        self.assertAlmostEqual(RenderQueue._progress_seconds("out_time_ms=1250000"), 1.25)
        self.assertAlmostEqual(RenderQueue._progress_seconds("out_time=00:00:01.250000"), 1.25)


if __name__ == "__main__":
    unittest.main()
