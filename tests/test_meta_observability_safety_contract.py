import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetaObservabilitySafetyContractTests(unittest.TestCase):
    def test_remote_paused_confirmation_requires_all_configured_status_objects(self):
        source = (ROOT / 'src' / 'binario_marketing' / 'meta_observability.py').read_text(encoding='utf-8')
        self.assertIn('configured_states: dict[str, bool | None] = {}', source)
        self.assertIn('required_status_objects = ("campaign", "adset", "ad")', source)
        self.assertIn('configured_states.get(kind) is True', source)
        self.assertIn('"configured_paused": complete_paused_evidence', source)
        self.assertNotIn('all(configured_paused) if configured_paused else None', source)


if __name__ == '__main__':
    unittest.main()
