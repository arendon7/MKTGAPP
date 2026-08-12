import tempfile
import unittest
from pathlib import Path

from binario_marketing.ai_gateway import AIGateway, GatewayRequest, GatewayResponse


class GatewayTests(unittest.TestCase):
    def test_usage_is_logged_without_memory_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            gateway = AIGateway(Path(tmp) / "usage.jsonl")
            gateway.register("fake", lambda request: GatewayResponse("ok", 10, 2, "req-1"))
            response = gateway.invoke(GatewayRequest("fake", "demo", "summarize", "hello", {"project": "p1"}))
            self.assertEqual(response.text, "ok")
            entries = gateway.ledger.entries()
            self.assertEqual(len(entries), 1)
            self.assertFalse(entries[0].payload["canonical_memory_write"])
            self.assertTrue(gateway.ledger.verify())


if __name__ == "__main__":
    unittest.main()
