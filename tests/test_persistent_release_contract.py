import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PersistentReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        self.publisher = (ROOT / "scripts/publish_release_transaction.sh").read_text(encoding="utf-8")

    def test_release_is_tag_driven_and_can_write_release_assets(self):
        self.assertIn('      - "v*"', self.workflow)
        self.assertIn("contents: write", self.workflow)
        self.assertIn("publish_release_transaction.sh", self.workflow)
        self.assertIn('gh release create "$GITHUB_REF_NAME"', self.publisher)
        self.assertIn("--verify-tag", self.publisher)
        self.assertIn("--draft", self.publisher)
        self.assertIn("--draft=false", self.publisher)

    def test_release_requires_both_native_mac_architectures(self):
        self.assertIn("runner: macos-15", self.workflow)
        self.assertIn("arch: arm64", self.workflow)
        self.assertIn("runner: macos-15-intel", self.workflow)
        self.assertIn("arch: x86_64", self.workflow)
        self.assertIn("needs: build-native", self.workflow)

    def test_release_assets_are_hashed_and_reverified_before_publish(self):
        self.assertIn("shasum -a 256", self.workflow)
        self.assertIn("sha256sum -c", self.workflow)
        self.assertIn("RELEASE-arm64.json", self.workflow)
        self.assertIn("RELEASE-x86_64.json", self.workflow)


if __name__ == "__main__":
    unittest.main()
