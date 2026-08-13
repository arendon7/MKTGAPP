import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class FakeObservability:
    def __init__(self):
        self.publication_rows = []
        self.paid_rows = []

    def publication(self, row):
        self.publication_rows.append(row)
        return {'publication_id': row.id, 'available': True, 'remote_state': 'READY', 'insights': {}}

    def paid_media(self, row, *, date_preset='maximum'):
        self.paid_rows.append((row, date_preset))
        return {
            'draft_id': row.id,
            'available': True,
            'date_preset': date_preset,
            'objects': {'ad': {'id': row.ad_id, 'observed_state': 'PAUSED'}},
            'insights': {'impressions': '12'},
            'safety': {'activation_endpoint_present': False, 'explicit_active_detected': False, 'configured_paused': True},
        }


class MetaObservabilityApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / 'data')
        self.server = create_server(self.runtime, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.project_id = self.runtime.create_project('Observability')['id']
        self.fake = FakeObservability()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def published_row(self):
        row = self.runtime.social.create(self.project_id, {
            'channel': 'facebook_page', 'target_id': 'page-1', 'target_name': 'Page One',
            'kind': 'text', 'message': 'Read only observability',
        })
        row = self.runtime.social.queue(row.id)
        row = self.runtime.social.transition(row.id, 'PUBLISHING')
        return self.runtime.social.transition(row.id, 'PUBLISHED', remote_id='page-1_post-1')

    def paid_row(self):
        row = self.runtime.paid_media.create(self.project_id, {
            'ad_account_id': '77', 'campaign_name': 'Observe campaign', 'campaign_objective': 'OUTCOME_TRAFFIC',
            'special_ad_categories': [], 'adset_name': 'Observe adset', 'daily_budget': 2100,
            'optimization_goal': 'LINK_CLICKS', 'targeting': {'geo_locations': {'countries': ['CO']}},
            'page_id': 'page-1', 'instagram_actor_id': None, 'creative_name': 'Observe creative',
            'message': 'Observe only', 'link_url': 'https://example.com', 'picture_url': 'https://cdn.example.com/a.jpg',
            'call_to_action': 'LEARN_MORE', 'ad_name': 'Observe ad',
        })
        for field, value in [('campaign_id', 'campaign-1'), ('adset_id', 'adset-1'), ('creative_id', 'creative-1'), ('ad_id', 'ad-1')]:
            row = self.runtime.paid_media.checkpoint_remote(row.id, field, value)
        return self.runtime.paid_media.mark_remote_paused(row.id)

    def test_publication_observability_is_project_scoped(self):
        row = self.published_row()
        with patch('binario_marketing.service.MetaObservability.from_env', return_value=self.fake):
            with urlopen(f'{self.base}/api/projects/{self.project_id}/publications/{row.id}/observability', timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload['publication_id'], row.id)
        self.assertEqual([item.id for item in self.fake.publication_rows], [row.id])

        other_id = self.runtime.create_project('Other')['id']
        with patch('binario_marketing.service.MetaObservability.from_env', return_value=self.fake):
            with self.assertRaises(HTTPError) as raised:
                urlopen(f'{self.base}/api/projects/{other_id}/publications/{row.id}/observability', timeout=5)
        self.assertEqual(raised.exception.code, 404)
        self.assertEqual(len(self.fake.publication_rows), 1)

    def test_paid_media_observability_propagates_safe_date_preset(self):
        row = self.paid_row()
        with patch('binario_marketing.service.MetaObservability.from_env', return_value=self.fake):
            with urlopen(f'{self.base}/api/projects/{self.project_id}/paid-media/{row.id}/observability?date_preset=last_30d', timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload['date_preset'], 'last_30d')
        self.assertEqual(payload['safety']['configured_paused'], True)
        self.assertEqual([(item.id, preset) for item, preset in self.fake.paid_rows], [(row.id, 'last_30d')])

    def test_observability_static_bundles_are_served_locally(self):
        with urlopen(f'{self.base}/meta-observability.js', timeout=5) as response:
            js = response.read().decode('utf-8')
            js_type = response.headers.get('Content-Type', '')
        with urlopen(f'{self.base}/meta-observability.css', timeout=5) as response:
            css = response.read().decode('utf-8')
            css_type = response.headers.get('Content-Type', '')
        self.assertIn('verifyMetaPublication', js)
        self.assertIn('READ ONLY', js)
        self.assertIn('meta-observability-card', css)
        self.assertIn('javascript', js_type)
        self.assertIn('text/css', css_type)


if __name__ == '__main__':
    unittest.main()
