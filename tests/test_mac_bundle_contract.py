import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MacBundleContractTests(unittest.TestCase):
    def test_runtime_pin_covers_both_mac_architectures_with_sha256(self):
        text = (ROOT / "scripts/full_mac_python_runtime.env").read_text(encoding="utf-8")
        self.assertIn("FULL_MAC_PYTHON_VERSION='3.12.13'", text)
        for key in ("ARM64", "X86_64"):
            match = re.search(rf"FULL_MAC_PYTHON_{key}_SHA256='([0-9a-f]{{64}})'", text)
            self.assertIsNotNone(match)
            self.assertIn(f"FULL_MAC_PYTHON_{key}_URL=", text)

    def test_app_launcher_executes_embedded_interpreter_in_isolated_mode(self):
        builder = (ROOT / "scripts/build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn('PYTHON="$RESOURCES/runtime/python/bin/python3"', builder)
        self.assertIn('exec "$PYTHON" -I -B "$RESOURCES/launch.py"', builder)
        self.assertIn('unset PYTHONHOME PYTHONPATH', builder)
        self.assertNotIn("command -v python3", builder)

    def test_builder_packages_git_source_directly(self):
        builder = (ROOT / "scripts/build_full_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn('ditto "$ROOT/src" "$SOURCE/src"', builder)
        self.assertIn('ditto "$ROOT/apps" "$SOURCE/apps"', builder)
        self.assertIn('ditto "$ROOT/web" "$SOURCE/web"', builder)
        self.assertNotIn("WAVE21", builder.upper())


if __name__ == "__main__":
    unittest.main()
