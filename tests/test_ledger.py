import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.ledger import JsonlLedger


class LedgerTests(unittest.TestCase):
    def test_hash_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.jsonl"
            ledger = JsonlLedger(path)
            ledger.append("a", {"value": 1})
            ledger.append("b", {"value": 2})
            self.assertTrue(ledger.verify())
            rows = path.read_text(encoding="utf-8").splitlines()
            payload = json.loads(rows[0])
            payload["payload"]["value"] = 999
            rows[0] = json.dumps(payload)
            path.write_text("\n".join(rows) + "\n", encoding="utf-8")
            self.assertFalse(ledger.verify())


if __name__ == "__main__":
    unittest.main()
