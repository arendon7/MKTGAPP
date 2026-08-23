from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_published_release_roundtrip.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"


def _module():
    spec = importlib.util.spec_from_file_location("wave93_roundtrip", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave93GithubReleaseRoundtripTests(unittest.TestCase):
    def test_exact_asset_bytes_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = root / "expected"
            downloaded = root / "downloaded"
            expected.mkdir(); downloaded.mkdir()
            for name, payload in (("a.zip", b"zip-bytes"), ("evidence.json", b"{}\n")):
                (expected / name).write_bytes(payload)
                (downloaded / name).write_bytes(payload)
            report = _module().verify(expected, downloaded, tag="v1.0.0", git_sha="a" * 40)
            self.assertTrue(report["draft_roundtrip_verified"])
            self.assertTrue(report["github_uploaded_bytes_match_authorized_local_bytes"])
            self.assertFalse(report["release_authority"])
            self.assertFalse(report["publication_authority"])
            self.assertFalse(report["production_ready"])

    def test_tampered_downloaded_asset_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); expected = root / "expected"; downloaded = root / "downloaded"
            expected.mkdir(); downloaded.mkdir()
            (expected / "a.zip").write_bytes(b"one")
            (downloaded / "a.zip").write_bytes(b"two")
            with self.assertRaisesRegex(ValueError, "byte mismatch"):
                _module().verify(expected, downloaded, tag="v1.0.0", git_sha="a" * 40)

    def test_missing_or_extra_asset_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); expected = root / "expected"; downloaded = root / "downloaded"
            expected.mkdir(); downloaded.mkdir()
            (expected / "a.zip").write_bytes(b"one")
            (downloaded / "b.zip").write_bytes(b"one")
            with self.assertRaisesRegex(ValueError, "inventory mismatch"):
                _module().verify(expected, downloaded, tag="v1.0.0", git_sha="a" * 40)

    def test_workflow_uses_draft_verify_then_publish_transaction(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("gh release create", source)
        self.assertIn("--draft", source)
        self.assertIn("gh release download", source)
        self.assertIn("verify_published_release_roundtrip.py", source)
        self.assertIn("GITHUB-RELEASE-ROUNDTRIP.json", source)
        self.assertIn("gh release upload", source)
        self.assertIn("gh release edit", source)
        self.assertIn("--draft=false", source)
        self.assertIn("gh release delete", source)
        create_at = source.index("gh release create")
        download_at = source.index("gh release download")
        verify_at = source.index("verify_published_release_roundtrip.py")
        publish_at = source.index("gh release edit")
        self.assertLess(create_at, download_at)
        self.assertLess(download_at, verify_at)
        self.assertLess(verify_at, publish_at)


if __name__ == "__main__":
    unittest.main()
