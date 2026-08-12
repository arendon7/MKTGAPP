import tempfile
import unittest
from pathlib import Path

from binario_marketing.projects import ProjectStore


class ProjectStoreTests(unittest.TestCase):
    def test_asset_import_and_x_delete_flow(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "video.mp4"
            source.write_bytes(b"fake-video")
            store = ProjectStore(root / "projects")
            project = store.create("Campaña Café")
            asset = store.add_asset(project.id, source, "video")
            managed = store.path_for(project.id) / asset.relative_path
            self.assertTrue(managed.exists())
            self.assertEqual(len(store.assets(project.id)), 1)
            self.assertTrue(store.remove_asset(project.id, asset.id))
            self.assertFalse(managed.exists())
            self.assertEqual(store.assets(project.id), [])


if __name__ == "__main__":
    unittest.main()
