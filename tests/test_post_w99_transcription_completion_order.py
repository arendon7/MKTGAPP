import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.projects import ProjectStore
from binario_marketing.transcription_manager import TranscriptionManager
from binario_marketing.workspace import Workspace


FAKE_FFMPEG = r'''#!__PYTHON__
import pathlib,sys
pathlib.Path(sys.argv[-1]).write_bytes(b'wav-data')
'''
FAKE_WHISPER = r'''#!__PYTHON__
import json,pathlib,sys
prefix=pathlib.Path(sys.argv[sys.argv.index('-of')+1])
prefix.with_suffix('.json').write_text(json.dumps({"result":{"language":"es"},"transcription":[{"start":0.0,"end":2.0,"text":"evidencia completa"}]}),encoding='utf-8')
'''


class TranscriptionCompletionOrderTests(unittest.TestCase):
    def test_pass_is_not_observable_before_completed_timeline_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            projects = ProjectStore(root / "projects")
            workspace = Workspace(root / "workspace")
            project = projects.create("Completion order")
            source = root / "video.mp4"
            source.write_bytes(b"video")
            asset = projects.add_asset(project.id, source, "video")
            ffmpeg = root / "ffmpeg"
            ffmpeg.write_text(FAKE_FFMPEG.replace("__PYTHON__", sys.executable), encoding="utf-8")
            ffmpeg.chmod(0o755)
            whisper = root / "whisper-cli"
            whisper.write_text(FAKE_WHISPER.replace("__PYTHON__", sys.executable), encoding="utf-8")
            whisper.chmod(0o755)
            model = root / "ggml-tiny.bin"
            model.write_bytes(b"model")
            manager = TranscriptionManager(
                root / "state",
                projects,
                workspace,
                ffmpeg=str(ffmpeg),
                whisper_cli=str(whisper),
                model=str(model),
            )
            completed_entered = threading.Event()
            allow_completed = threading.Event()
            original_append = workspace.registries.timeline.append

            def guarded_append(kind, payload):
                if kind == "transcription.completed":
                    completed_entered.set()
                    if not allow_completed.wait(timeout=3):
                        raise RuntimeError("test did not release completed evidence")
                return original_append(kind, payload)

            try:
                with patch.object(workspace.registries.timeline, "append", side_effect=guarded_append):
                    manager.ensure(project.id, asset.id, "auto")
                    self.assertTrue(completed_entered.wait(timeout=3))
                    current = manager.get(project.id, asset.id)
                    self.assertIsNotNone(current)
                    self.assertEqual(current.status, "TRANSCRIBING")
                    allow_completed.set()
                    deadline = time.time() + 3
                    while time.time() < deadline:
                        current = manager.get(project.id, asset.id)
                        if current and current.status == "PASS":
                            break
                        time.sleep(0.01)
                    self.assertEqual(current.status, "PASS")
                    events = [entry.kind for entry in workspace.registries.timeline.entries()]
                    self.assertIn("transcription.completed", events)
            finally:
                allow_completed.set()
                manager.shutdown()


if __name__ == "__main__":
    unittest.main()
