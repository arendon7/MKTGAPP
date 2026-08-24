import subprocess
import sys
import unittest
from pathlib import Path

from binario_marketing import __version__
from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.version import MACOS_BUNDLE_VERSION, MACOS_SHORT_VERSION, RELEASE_READY, RELEASE_TAG


ROOT = Path(__file__).resolve().parents[1]


class VersionContractTests(unittest.TestCase):
    def test_package_version_has_single_dynamic_source(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        init = (ROOT / "src/binario_marketing/__init__.py").read_text(encoding="utf-8")
        self.assertIn('dynamic = ["version"]', pyproject)
        self.assertIn('version = {attr = "binario_marketing.version.__version__"}', pyproject)
        self.assertNotIn('version = "0.9.0"', pyproject)
        self.assertIn("from .version import __version__", init)
        self.assertEqual(__version__, "0.9.0")

    def test_macos_version_fields_are_explicit_and_valid(self):
        self.assertRegex(MACOS_SHORT_VERSION, r"^[0-9]+(?:\.[0-9]+){1,2}$")
        self.assertRegex(MACOS_BUNDLE_VERSION, r"^[0-9]+(?:\.[0-9]+){0,2}$")
        self.assertEqual(MACOS_SHORT_VERSION, __version__)

    def test_full_mac_builder_consumes_canonical_version(self):
        builder = (ROOT / "scripts/build_full_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts/audit_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("from binario_marketing.version import MACOS_BUNDLE_VERSION, MACOS_SHORT_VERSION, __version__", builder)
        self.assertIn('<key>CFBundleShortVersionString</key><string>$MACOS_SHORT_VERSION</string>', builder)
        self.assertIn('<key>CFBundleVersion</key><string>$MACOS_BUNDLE_VERSION</string>', builder)
        self.assertNotIn('<key>CFBundleShortVersionString</key><string>0.9.0</string>', builder)
        self.assertIn("provenance['product_version'] == __version__", audit)
        self.assertIn("plist_short == MACOS_SHORT_VERSION", audit)
        self.assertIn("plist_build == MACOS_BUNDLE_VERSION", audit)

    def test_release_source_is_prepared_but_not_operationally_authorized(self):
        self.assertTrue(RELEASE_READY)
        self.assertEqual(RELEASE_TAG, "v0.9.0")
        self.assertEqual(source_release_state(), PREPARED_RELEASE)
        readiness = source_release_readiness()
        self.assertTrue(readiness["source_ready"])
        self.assertEqual(readiness["stage"], "SOURCE_CONTRACT_READY")
        self.assertFalse(readiness["operational_inputs_complete"])
        self.assertFalse(readiness["production_ready"])

        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify_release_tag.py"), "--tag", RELEASE_TAG],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("RELEASE TAG PASS", proc.stdout)

        mismatch = subprocess.run(
            [sys.executable, str(ROOT / "scripts/verify_release_tag.py"), "--tag", "v0.9.1"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertEqual(mismatch.returncode, 4)
        self.assertIn("tag mismatch", mismatch.stderr)

    def test_persistent_release_has_preflight_before_native_builds(self):
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        self.assertIn("release-preflight:", workflow)
        self.assertIn('python scripts/verify_release_tag.py --tag "$GITHUB_REF_NAME"', workflow)
        self.assertIn("needs: release-preflight", workflow)

    def test_source_ci_covers_chore_branches_and_shell_syntax(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn('"chore/**"', workflow)
        self.assertIn("Shell syntax", workflow)
        self.assertIn('bash -n "$script"', workflow)
        self.assertIn("python scripts/version_info.py", workflow)


if __name__ == "__main__":
    unittest.main()
