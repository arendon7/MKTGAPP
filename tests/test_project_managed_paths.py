import tempfile
import unittest
from pathlib import Path

from binario_marketing.projects import ProjectStore


class ProjectManagedPathTests(unittest.TestCase):
    def test_asset_metadata_can_be_removed_if_managed_file_was_deleted_externally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "video.mp4"
            source.write_bytes(b"video")
            store = ProjectStore(root / "projects")
            project = store.create("Managed")
            asset = store.add_asset(project.id, source, "video")
            managed = store.asset_path(project.id, asset.id)
            managed.unlink()
            self.assertTrue(store.remove_asset(project.id, asset.id))
            self.assertEqual(store.assets(project.id), [])

    def test_export_filename_is_forced_to_managed_basename(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(Path(tmp) / "projects")
            project = store.create("Exports")
            path = store.export_path(project.id, "../../outside.mp4")
            self.assertEqual(path.name, "outside.mp4")
            self.assertEqual(path.parent, store.exports_dir(project.id).resolve())


if __name__ == "__main__":
    unittest.main()
