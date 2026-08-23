from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_wave93_draft_publication_transaction.sh"


class Wave93StaticAuditTests(unittest.TestCase):
    def test_static_transaction_audit_passes(self):
        completed = subprocess.run(
            ["bash", str(AUDIT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertIn("WAVE 93 DRAFT PUBLICATION TRANSACTION AUDIT PASS", completed.stdout)


if __name__ == "__main__":
    unittest.main()
