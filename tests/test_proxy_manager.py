import hashlib
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

from binario_marketing.projects import ProjectStore
from binario_marketing.proxy_manager import ProxyManager
from binario_marketing.workspace import Workspace


FAKE_FFMPEG = r'''#!__PYTHON__
import pathlib, sys, time
time.sleep(0.04)
pathlib.Path(sys.argv[-1]).write_bytes(b"proxy-video")
'''

FAKE_FFPROBE = r'''#!__PYTHON__
import json
print(json.dumps({"streams":[{"codec_type":"video","width":1920,"height":1080}],"format":{"duration":"10.0"}}))
'''


class ProxyManagerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.projects = ProjectStore(self.root / "projects")
        self.workspace = Workspace(self.root / "workspace")
        self.project = self.projects.create("Proxy")
        source = self.root / "source.mp4"
        source.write_bytes(b"source-video")
        self.asset = self.projects.add_asset(self.project.id, source, "video")
        self.ffmpeg = self.root / "fake-ffmpeg"
        self.ffmpeg.write_text(FAKE_FFMPEG.replace("__PYTHON__", sys.executable), encoding="utf-8")
        self.ffmpeg.chmod(0o755)
        self.ffprobe = self.root / "fake-ffprobe"
        self.ffprobe.write_text(FAKE_FFPROBE.replace("__PYTHON__", sys.executable), encoding="utf-8")
        self.ffprobe.chmod(0o755)
        self.old_ffprobe = os.environ.get("BINARIO_FFPROBE")
        os.environ["BINARIO_FFPROBE"] = str(self.ffprobe)
        self.manager = ProxyManager(self.root / "proxy-state", self.projects, self.workspace, str(self.ffmpeg), video_codec="mpeg4")

    def tearDown(self):
        self.manager.shutdown()
        if self.old_ffprobe is None:
            os.environ.pop("BINARIO_FFPROBE", None)
        else:
            os.environ["BINARIO_FFPROBE"] = self.old_ffprobe
        self.tmp.cleanup()

    def wait_terminal(self, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            row = self.manager.get(self.project.id, self.asset.id)
            if row and row.status in {"PASS", "FAIL", "CANCELLED", "INTERRUPTED"}:
                return row
            time.sleep(0.02)
        self.fail("proxy did not reach terminal state")

    def test_proxy_is_sha_addressed_cached_and_confined(self):
        queued = self.manager.ensure(self.project.id, self.asset.id)
        self.assertIn(queued.status, {"PENDING", "RUNNING", "PASS"})
        done = self.wait_terminal()
        self.assertEqual(done.status, "PASS", done.error)
        self.assertIn(self.asset.sha256[:12], done.filename)
        path = self.manager.file_path(self.project.id, self.asset.id)
        self.assertEqual(path.parent, self.projects.proxies_dir(self.project.id).resolve())
        self.assertEqual(done.sha256, hashlib.sha256(b"proxy-video").hexdigest())
        self.assertTrue(done.artifact_ref)
        cached = self.manager.ensure(self.project.id, self.asset.id)
        self.assertEqual(cached.created_at, done.created_at)
        self.assertEqual(cached.filename, done.filename)
        self.assertTrue(self.workspace.registries.verify_all())

    def test_invalidate_removes_derived_proxy_not_source(self):
        self.manager.ensure(self.project.id, self.asset.id)
        self.wait_terminal()
        proxy = self.manager.file_path(self.project.id, self.asset.id)
        source = self.projects.asset_path(self.project.id, self.asset.id)
        self.manager.invalidate(self.project.id, self.asset.id)
        self.assertFalse(proxy.exists())
        self.assertTrue(source.exists())
        self.assertIsNone(self.manager.get(self.project.id, self.asset.id))

    def test_missing_ffmpeg_fails_without_spawning_proxy(self):
        other = ProxyManager(self.root / "missing-state", self.projects, self.workspace, str(self.root / "missing-ffmpeg"), video_codec="mpeg4")
        row = other.ensure(self.project.id, self.asset.id)
        self.assertEqual(row.status, "FAIL")
        self.assertIn("ffmpeg executable unavailable", row.error)
        other.shutdown()

    def test_proxy_path_forces_managed_basename(self):
        path = self.projects.proxy_path(self.project.id, "../escape.mp4")
        self.assertEqual(path.name, "escape.mp4")
        self.assertEqual(path.parent, self.projects.proxies_dir(self.project.id).resolve())


if __name__ == "__main__":
    unittest.main()
