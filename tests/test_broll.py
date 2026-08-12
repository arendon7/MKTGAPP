import unittest

from binario_marketing.video.broll import BrollAsset, contextual_broll


class BrollTests(unittest.TestCase):
    def test_contextual_selection_prefers_matching_tags(self):
        assets = [
            BrollAsset("coffee", ("café", "cultivo")),
            BrollAsset("office", ("oficina", "equipo")),
        ]
        selected = contextual_broll("El cultivo de café mejora", assets)
        self.assertEqual([item.id for item in selected], ["coffee"])


if __name__ == "__main__":
    unittest.main()
