from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_wave95_prepared_release_sha_stability.sh"


class Wave95StaticAuditTests(unittest.TestCase):
    def test_wave95_static_audit_passes(self):
        result = subprocess.run(
            ["bash", str(AUDIT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
        self.assertIn("WAVE 95 PREPARED RELEASE SHA STABILITY AUDIT PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
