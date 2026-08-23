from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_published_release_roundtrip.py"
TRANSACTION = ROOT / "scripts" / "publish_release_transaction.sh"
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

    def test_workflow_uses_delegated_draft_verify_then_publish_transaction(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        transaction = TRANSACTION.read_text(encoding="utf-8")
        self.assertIn("bash scripts/publish_release_transaction.sh", workflow)
        for token in (
            "gh release create",
            "--draft",
            "gh release upload",
            "gh release download",
            "verify_published_release_roundtrip.py",
            "GITHUB-RELEASE-ROUNDTRIP.json",
            "GITHUB-RELEASE-FINAL-VERIFY.json",
            "gh release edit",
            "--draft=false",
            "gh release delete",
        ):
            self.assertIn(token, transaction)
        create_at = transaction.index("gh release create")
        first_upload_at = transaction.index('gh release upload "$GITHUB_REF_NAME" release/*')
        first_download_at = transaction.index("gh release download")
        first_verify_at = transaction.index("verify_published_release_roundtrip.py")
        evidence_upload_at = transaction.index('gh release upload "$GITHUB_REF_NAME" .release-transaction/GITHUB-RELEASE-ROUNDTRIP.json')
        final_download_at = transaction.index("gh release download", first_download_at + 1)
        final_verify_at = transaction.index("verify_published_release_roundtrip.py", first_verify_at + 1)
        publish_at = transaction.index("gh release edit")
        self.assertTrue(
            create_at < first_upload_at < first_download_at < first_verify_at < evidence_upload_at < final_download_at < final_verify_at < publish_at
        )

    def test_partial_upload_failure_is_cleanup_eligible(self):
        transaction = TRANSACTION.read_text(encoding="utf-8")
        preflight = transaction.index('gh release view "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1')
        attempted = transaction.index("CREATE_ATTEMPTED=1")
        create = transaction.index("gh release create")
        upload = transaction.index('gh release upload "$GITHUB_REF_NAME" release/*')
        self.assertTrue(preflight < attempted < create < upload)
        self.assertIn('"$CREATE_ATTEMPTED" == "1"', transaction)
        self.assertIn('"$TRANSACTION_COMPLETE" != "1"', transaction)
        self.assertIn("--json isDraft", transaction)
        self.assertIn('if [[ "$is_draft" == "true" ]]', transaction)
        self.assertIn("gh release delete", transaction)
        self.assertIn("TRANSACTION_COMPLETE=1", transaction)

    def test_final_public_inventory_includes_roundtrip_evidence(self):
        transaction = TRANSACTION.read_text(encoding="utf-8")
        self.assertIn("cp release/* github-release-expected/", transaction)
        self.assertIn("cp .release-transaction/GITHUB-RELEASE-ROUNDTRIP.json github-release-expected/", transaction)
        self.assertIn("--expected-dir github-release-expected", transaction)
        self.assertIn("--downloaded-dir github-release-final", transaction)


if __name__ == "__main__":
    unittest.main()
