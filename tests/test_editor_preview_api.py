import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from binario_marketing.service import AppRuntime, create_server, parse_byte_range


ROOT = Path(__file__).resolve().parents[1]


class ByteRangeTests(unittest.TestCase):
    def test_normal_open_and_suffix_ranges(self):
        self.assertEqual(parse_byte_range("bytes=10-19", 100), (10, 19))
        self.assertEqual(parse_byte_range("bytes=90-", 100), (90, 99))
        self.assertEqual(parse_byte_range("bytes=-10", 100), (90, 99))
        self.assertEqual(parse_byte_range("bytes=90-999", 100), (90, 99))

    def test_invalid_ranges_fail_closed(self):
        for value in ("bytes=", "bytes=50-20", "bytes=100-", "items=0-1", "bytes=0-1,4-5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_byte_range(value, 100)


class EditorPreviewApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        project = self.runtime.create_project("Preview")
        self.project_id = project["id"]
        self.payload = bytes(range(256)) * 8
        url = f"{self.base}/api/projects/{self.project_id}/assets/upload?filename={quote('preview.mp4')}&kind=video"
        req = Request(url, data=self.payload, method="POST", headers={"Content-Type": "video/mp4"})
        with urlopen(req, timeout=5) as response:
            import json
            self.asset = json.loads(response.read())

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        self.tmp.cleanup()

    def test_asset_file_supports_browser_range_streaming(self):
        path = f"{self.base}/api/projects/{self.project_id}/assets/{self.asset['id']}/file"
        with urlopen(path, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Accept-Ranges"], "bytes")
            self.assertEqual(response.read(), self.payload)
        req = Request(path, headers={"Range": "bytes=10-29"})
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], f"bytes 10-29/{len(self.payload)}")
            self.assertEqual(response.read(), self.payload[10:30])
        req = Request(path, headers={"Range": "bytes=-12"})
        with urlopen(req, timeout=5) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.read(), self.payload[-12:])

    def test_unsatisfiable_range_returns_416_without_leaking_path(self):
        path = f"{self.base}/api/projects/{self.project_id}/assets/{self.asset['id']}/file"
        req = Request(path, headers={"Range": f"bytes={len(self.payload)}-"})
        with self.assertRaises(HTTPError) as raised:
            urlopen(req, timeout=5)
        self.assertEqual(raised.exception.code, 416)
        self.assertEqual(raised.exception.headers["Content-Range"], f"bytes */{len(self.payload)}")

    def test_project_detail_exposes_managed_paths_and_reveal_is_id_scoped(self):
        detail = self.runtime.project_detail(self.project_id)
        root = self.runtime.projects.path_for(self.project_id).resolve()
        self.assertEqual(detail["paths"]["project"], str(root))
        self.assertEqual(detail["paths"]["exports"], str((root / "exports").resolve()))
        with patch("binario_marketing.service.platform.system", return_value="Darwin"), patch("binario_marketing.service.subprocess.run") as run:
            result = self.runtime.reveal_project(self.project_id)
        self.assertTrue(result["opened"])
        run.assert_called_once_with(["/usr/bin/open", str(root)], check=True, timeout=10)

    def test_completed_render_no_longer_blocks_source_asset_delete(self):
        asset_id = self.asset["id"]
        with patch.object(self.runtime.renders, "list", return_value=[SimpleNamespace(asset_id=asset_id, status="PASS")]):
            self.runtime.remove_asset(self.project_id, asset_id)
        self.assertEqual(self.runtime.projects.assets(self.project_id), [])

    def test_active_render_still_blocks_source_asset_delete(self):
        asset_id = self.asset["id"]
        with patch.object(self.runtime.renders, "list", return_value=[SimpleNamespace(asset_id=asset_id, status="RUNNING")]):
            with self.assertRaisesRegex(ValueError, "active render"):
                self.runtime.remove_asset(self.project_id, asset_id)


if __name__ == "__main__":
    unittest.main()
