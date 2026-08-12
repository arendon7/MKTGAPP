import tempfile
import unittest
from pathlib import Path

from binario_marketing.app_factory import AppFactoryRegistry


class AppFactoryTests(unittest.TestCase):
    def test_stage_registry_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            registry = AppFactoryRegistry(Path(tmp))
            registry.upsert("p1", "Landing", "product_lab")
            registry.upsert("p1", "Landing", "engineering_delivery")
            rows = registry.list()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].stage, "engineering_delivery")


if __name__ == "__main__":
    unittest.main()
