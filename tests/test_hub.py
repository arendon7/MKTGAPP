import unittest
from pathlib import Path

from binario_marketing.hub import discover_apps


ROOT = Path(__file__).resolve().parents[1]


class HubTests(unittest.TestCase):
    def test_recovered_manifests_are_discoverable_and_unique(self):
        apps = discover_apps(ROOT)
        ids = {app.app_id for app in apps}
        self.assertIn("editor-video-ia", ids)
        self.assertIn("app-factory-ia", ids)
        self.assertEqual(len(ids), len(apps))


if __name__ == "__main__":
    unittest.main()
