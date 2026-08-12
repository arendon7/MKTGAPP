import tempfile
import unittest
from pathlib import Path

from binario_marketing.editor_store import EditorStore


class EditorStoreTests(unittest.TestCase):
    def test_state_and_undo_history_survive_store_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = EditorStore(root)
            first.apply("p1", "add_clip", {"asset_id": "a1", "start": 0, "end": 20})
            first.apply("p1", "aspect", {"value": "9:16"})
            self.assertEqual(first.state("p1")["aspect_ratio"], "9:16")

            restarted = EditorStore(root)
            self.assertEqual(len(restarted.state("p1")["clips"]), 1)
            self.assertEqual(restarted.state("p1")["aspect_ratio"], "9:16")
            restarted.apply("p1", "undo", {})
            self.assertEqual(restarted.state("p1")["aspect_ratio"], "16:9")
            restarted.apply("p1", "undo", {})
            self.assertEqual(restarted.state("p1")["clips"], [])
            restarted.apply("p1", "redo", {})
            self.assertEqual(len(restarted.state("p1")["clips"]), 1)


if __name__ == "__main__":
    unittest.main()
