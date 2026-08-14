import io
import tempfile
import unittest
from pathlib import Path

from binario_marketing.company_media_store import CompanyMediaStore


COMPANY_A = "company_" + "a" * 24
COMPANY_B = "company_" + "b" * 24


class CompanyMediaStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.store = CompanyMediaStore(root / "State" / "records", root / "CompanyMedia")

    def tearDown(self):
        self.tmp.cleanup()

    def test_upload_hashes_and_confines_file_to_company(self):
        body = b"managed-video-evidence"
        row = self.store.add_uploaded(COMPANY_A, "../My Reel.MP4", "video", io.BytesIO(body), len(body))
        self.assertEqual(row.company_id, COMPANY_A)
        self.assertEqual(row.original_name, "My Reel.MP4")
        self.assertTrue(row.stored_name.startswith(row.id))
        self.assertEqual(row.bytes, len(body))
        path = self.store.verify_file(COMPANY_A, row.id)
        self.assertEqual(path.read_bytes(), body)
        self.assertEqual(path.parent.name, COMPANY_A)
        self.assertNotIn("..", row.stored_name)

    def test_company_boundary_is_enforced(self):
        body = b"image"
        row = self.store.add_uploaded(COMPANY_A, "photo.png", "image", io.BytesIO(body), len(body))
        with self.assertRaises(KeyError):
            self.store.get_for_company(COMPANY_B, row.id)
        with self.assertRaises(KeyError):
            self.store.path_for(COMPANY_B, row.id)
        self.assertEqual(self.store.list(COMPANY_B), [])

    def test_probe_metadata_is_durable_and_delete_removes_managed_file(self):
        body = b"video"
        row = self.store.add_uploaded(COMPANY_A, "reel.mov", "video", io.BytesIO(body), len(body))
        updated = self.store.update_probe(COMPANY_A, row.id, width=1080, height=1920, duration=12.5)
        self.assertEqual((updated.width, updated.height, updated.duration), (1080, 1920, 12.5))
        path = self.store.path_for(COMPANY_A, row.id)
        removed = self.store.remove(COMPANY_A, row.id)
        self.assertEqual(removed.id, row.id)
        self.assertFalse(path.exists())
        with self.assertRaises(KeyError):
            self.store.get(row.id)

    def test_rejects_unsupported_types_and_truncated_uploads(self):
        with self.assertRaises(ValueError):
            self.store.add_uploaded(COMPANY_A, "archive.zip", "video", io.BytesIO(b"x"), 1)
        with self.assertRaises(ValueError):
            self.store.add_uploaded(COMPANY_A, "clip.mp4", "video", io.BytesIO(b"x"), 2)


if __name__ == "__main__":
    unittest.main()
