import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.paid_media_store import PaidMediaStore


class PaidMediaStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = PaidMediaStore(Path(self.tmp.name))
        self.payload = {
            'ad_account_id': '77',
            'campaign_name': 'Agosto tráfico',
            'campaign_objective': 'OUTCOME_TRAFFIC',
            'special_ad_categories': [],
            'adset_name': 'Colombia 21-55',
            'daily_budget': 2100,
            'optimization_goal': 'LINK_CLICKS',
            'targeting': {'age_min': 21, 'age_max': 55, 'geo_locations': {'countries': ['CO']}},
            'page_id': 'page-1',
            'instagram_actor_id': 'ig-1',
            'creative_name': 'Creative producto',
            'message': 'Conoce el producto',
            'link_url': 'https://example.com/producto',
            'picture_url': 'https://cdn.example.com/producto.jpg',
            'call_to_action': 'LEARN_MORE',
            'ad_name': 'Ad producto A',
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_draft_persists_decisions_and_survives_store_restart(self):
        row = self.store.create('project-1', self.payload)
        self.assertEqual(row.status, 'DRAFT')
        restarted = PaidMediaStore(Path(self.tmp.name))
        loaded = restarted.get(row.id)
        self.assertEqual(loaded.daily_budget, 2100)
        self.assertEqual(loaded.targeting['geo_locations']['countries'], ['CO'])
        self.assertEqual(loaded.campaign_objective, 'OUTCOME_TRAFFIC')

    def test_credentials_are_rejected_and_never_written(self):
        payload = dict(self.payload, access_token='never-write-me')
        with self.assertRaisesRegex(ValueError, 'credentials must not be persisted'):
            self.store.create('project-1', payload)
        self.assertEqual(list(Path(self.tmp.name).glob('*.json')), [])

    def test_remote_hierarchy_can_only_be_marked_complete_when_all_ids_exist(self):
        row = self.store.create('project-1', self.payload)
        with self.assertRaisesRegex(ValueError, 'all remote Meta object ids'):
            self.store.mark_remote_paused(row.id, campaign_id='campaign-1', adset_id='', creative_id='creative-1', ad_id='ad-1')
        updated = self.store.mark_remote_paused(
            row.id,
            campaign_id='campaign-1',
            adset_id='adset-1',
            creative_id='creative-1',
            ad_id='ad-1',
        )
        self.assertEqual(updated.status, 'REMOTE_PAUSED')
        with self.assertRaises(ValueError):
            self.store.cancel(updated.id)

    def test_persisted_draft_has_no_activation_state_or_secret(self):
        row = self.store.create('project-1', self.payload)
        raw = json.loads((Path(self.tmp.name) / f'{row.id}.json').read_text(encoding='utf-8'))
        encoded = json.dumps(raw).lower()
        self.assertNotIn('access_token', encoded)
        self.assertNotIn('"active"', encoded)
        self.assertEqual(raw['status'], 'DRAFT')


if __name__ == '__main__':
    unittest.main()
