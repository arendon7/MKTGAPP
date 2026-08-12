import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.projects import ProjectStore


class ProjectUploadTests(unittest.TestCase):
    def test_stream_upload_records_sha_size_and_safe_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(Path(tmp) / "projects")
            project = store.create("Upload")
            body = b"0123456789" * 1000
            asset = store.add_uploaded_asset(project.id, "../Video Demo.MP4", "video", io.BytesIO(body), len(body))
            self.assertEqual(asset.name, "Video Demo.MP4")
            self.assertEqual(asset.bytes, len(body))
            self.assertEqual(asset.sha256, hashlib.sha256(body).hexdigest())
            managed = store.path_for(project.id) / asset.relative_path
            self.assertEqual(managed.read_bytes(), body)
            self.assertNotIn("..", asset.relative_path)

    def test_short_upload_is_rejected_and_partial_file_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(Path(tmp) / "projects")
            project = store.create("Broken")
            with self.assertRaises(ValueError):
                store.add_uploaded_asset(project.id, "broken.mp4", "video", io.BytesIO(b"abc"), 10)
            self.assertEqual(store.assets(project.id), [])
            assets_dir = store.path_for(project.id) / "assets"
            self.assertEqual(list(assets_dir.iterdir()), [])

    def test_legacy_asset_rows_without_hash_metadata_remain_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = ProjectStore(Path(tmp) / "projects")
            project = store.create("Legacy")
            path = store.path_for(project.id) / "assets.json"
            path.write_text(json.dumps([{"id":"a1","name":"old.mov","kind":"video","relative_path":"assets/a1-old.mov","imported_at":"2026-01-01T00:00:00+00:00"}]), encoding="utf-8")
            asset = store.assets(project.id)[0]
            self.assertIsNone(asset.sha256)
            self.assertIsNone(asset.bytes)


if __name__ == "__main__":
    unittest.main()
