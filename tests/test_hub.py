import unittest
from pathlib import Path

from binario_marketing.hub import discover_apps


ROOT = Path(__file__).resolve().parents[1]


class HubTests(unittest.TestCase):
    def test_recovered_inventory_is_12_apps_and_unique(self):
        apps = discover_apps(ROOT)
        ids = {app.app_id for app in apps}
        self.assertEqual(len(apps), 12)
        self.assertEqual(len(ids), 12)
        self.assertIn("05-editor-video-ia", ids)
        self.assertIn("12-app-factory-ia", ids)


if __name__ == "__main__":
    unittest.main()
