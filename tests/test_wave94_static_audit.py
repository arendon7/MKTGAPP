from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_wave94_ci_provenance_handoff.sh"


class Wave94StaticAuditTests(unittest.TestCase):
    def test_static_ci_provenance_handoff_audit_passes(self):
        result = subprocess.run(
            ["bash", str(AUDIT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("WAVE 94 CI PROVENANCE HANDOFF AUDIT PASS", result.stdout)


if __name__ == "__main__":
    unittest.main()
