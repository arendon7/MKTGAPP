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

    def test_remote_hierarchy_is_checkpointed_in_order_and_resumable(self):
        row = self.store.create('project-1', self.payload)
        with self.assertRaisesRegex(ValueError, 'campaign_id first'):
            self.store.checkpoint_remote(row.id, 'adset_id', 'adset-1')
        row = self.store.checkpoint_remote(row.id, 'campaign_id', 'campaign-1')
        self.assertEqual(row.campaign_id, 'campaign-1')
        self.assertIsNone(row.adset_id)
        restarted = PaidMediaStore(Path(self.tmp.name))
        row = restarted.checkpoint_remote(row.id, 'campaign_id', 'campaign-1')
        self.assertEqual(row.campaign_id, 'campaign-1')
        with self.assertRaisesRegex(ValueError, 'immutable'):
            restarted.checkpoint_remote(row.id, 'campaign_id', 'different-campaign')
        row = restarted.checkpoint_remote(row.id, 'adset_id', 'adset-1')
        row = restarted.checkpoint_remote(row.id, 'creative_id', 'creative-1')
        with self.assertRaisesRegex(ValueError, 'remote Meta objects'):
            restarted.cancel(row.id)
        with self.assertRaisesRegex(ValueError, 'all remote Meta object ids'):
            restarted.mark_remote_paused(row.id)
        row = restarted.checkpoint_remote(row.id, 'ad_id', 'ad-1')
        row = restarted.mark_remote_paused(row.id)
        self.assertEqual(row.status, 'REMOTE_PAUSED')
        self.assertEqual((row.campaign_id, row.adset_id, row.creative_id, row.ad_id), ('campaign-1', 'adset-1', 'creative-1', 'ad-1'))

    def test_persisted_draft_has_no_activation_state_or_secret(self):
        row = self.store.create('project-1', self.payload)
        raw = json.loads((Path(self.tmp.name) / f'{row.id}.json').read_text(encoding='utf-8'))
        encoded = json.dumps(raw).lower()
        self.assertNotIn('access_token', encoded)
        self.assertNotIn('"active"', encoded)
        self.assertEqual(raw['status'], 'DRAFT')


if __name__ == '__main__':
    unittest.main()
