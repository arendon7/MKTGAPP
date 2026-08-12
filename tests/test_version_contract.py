import subprocess
import sys
import unittest
from pathlib import Path

from binario_marketing import __version__
from binario_marketing.version import MACOS_BUNDLE_VERSION, MACOS_SHORT_VERSION, RELEASE_READY, RELEASE_TAG


ROOT = Path(__file__).resolve().parents[1]


class VersionContractTests(unittest.TestCase):
    def test_package_version_has_single_dynamic_source(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        init = (ROOT / "src/binario_marketing/__init__.py").read_text(encoding="utf-8")
        self.assertIn('dynamic = ["version"]', pyproject)
        self.assertIn('version = {attr = "binario_marketing.version.__version__"}', pyproject)
        self.assertNotIn('version = "0.9.0.dev1"', pyproject)
        self.assertIn("from .version import __version__", init)
        self.assertEqual(__version__, "0.9.0.dev1")

    def test_macos_version_fields_are_explicit_and_valid(self):
        self.assertRegex(MACOS_SHORT_VERSION, r"^[0-9]+(?:\.[0-9]+){1,2}$")
        self.assertRegex(MACOS_BUNDLE_VERSION, r"^[0-9]+(?:\.[0-9]+){0,2}$")

    def test_release_is_fail_closed_until_explicitly_certified(self):
        self.assertFalse(RELEASE_READY)
        self.assertIsNone(RELEASE_TAG)
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify_release_tag.py"), "--tag", f"v{__version__}"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 4)
        self.assertIn("release publishing is disabled", proc.stderr)

    def test_persistent_release_has_preflight_before_native_builds(self):
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        self.assertIn("release-preflight:", workflow)
        self.assertIn('python scripts/verify_release_tag.py --tag "$GITHUB_REF_NAME"', workflow)
        self.assertIn("needs: release-preflight", workflow)


if __name__ == "__main__":
    unittest.main()
