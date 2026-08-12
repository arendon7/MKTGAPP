import tempfile
import unittest
from pathlib import Path

from binario_marketing.workspace import Workspace


class WorkspaceTests(unittest.TestCase):
    def test_project_handoff_and_unified_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Workspace(Path(tmp))
            workspace.upsert_project("p1", "Campaña", "05-editor-video-ia")
            evidence = workspace.registries.record_evidence({"summary": "clip aprobado"})
            artifact = workspace.registries.record_artifact({"name": "clip-01.mp4"})
            handoff = workspace.handoff("p1", "05-editor-video-ia", "09-propuestas-ia", "usar clip aprobado", (artifact.hash,), (evidence.hash,))
            self.assertEqual(handoff.project_id, "p1")
            self.assertTrue(workspace.registries.verify_all())
            kinds = [entry.kind for entry in workspace.registries.timeline.entries()]
            self.assertIn("workspace.handoff", kinds)
            self.assertIn("evidence.recorded", kinds)
            self.assertIn("artifact.recorded", kinds)


if __name__ == "__main__":
    unittest.main()
