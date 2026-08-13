import unittest

from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.meta_observability import MetaObservability
from binario_marketing.paid_media_store import PaidMediaDraft
from binario_marketing.social_store import Publication


class FakeTransport:
    def __init__(self, *, active_ad=False):
        self.calls = []
        self.active_ad = active_ad

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        path = url.split('/v25.0/', 1)[-1]
        if path == 'me/accounts':
            return {
                'data': [{
                    'id': 'page-1',
                    'name': 'Page One',
                    'access_token': 'page-secret',
                    'instagram_business_account': {'id': 'ig-1', 'username': 'igone'},
                }]
            }
        if path == 'ig-media-1':
            return {
                'id': 'ig-media-1',
                'media_type': 'VIDEO',
                'media_product_type': 'REELS',
                'permalink': 'https://instagram.example/reel/1',
                'timestamp': '2026-08-13T00:00:00+0000',
            }
        if path == 'ig-media-1/insights':
            metrics = params.get('metric', '').split(',')
            return {'data': [{'name': metric, 'period': 'lifetime', 'values': [{'value': index + 1}]} for index, metric in enumerate(metrics)]}
        if path == 'fb-reel-1':
            return {'id': 'fb-reel-1', 'status': {'video_status': 'ready', 'processing_progress': 100}}
        if path == 'campaign-1':
            return {'id': 'campaign-1', 'name': 'Campaign', 'configured_status': 'PAUSED', 'effective_status': 'PAUSED'}
        if path == 'adset-1':
            return {'id': 'adset-1', 'name': 'Ad Set', 'status': 'PAUSED', 'effective_status': 'CAMPAIGN_PAUSED'}
        if path == 'creative-1':
            return {'id': 'creative-1', 'name': 'Creative'}
        if path == 'ad-1':
            status = 'ACTIVE' if self.active_ad else 'PAUSED'
            return {'id': 'ad-1', 'name': 'Ad', 'status': status, 'effective_status': status}
        if path == 'ad-1/insights':
            return {'data': [{'ad_id': 'ad-1', 'impressions': '120', 'reach': '98', 'clicks': '7', 'spend': '0'}]}
        raise AssertionError(f'unexpected Meta path: {path}')


def publication(**changes):
    payload = dict(
        id='pub-1', project_id='project-1', channel='instagram', target_id='ig-1', target_name='@igone',
        kind='reel', message='hello', link_url=None, media_url='https://cdn.example/reel.mp4', asset_id=None,
        scheduled_for=None, status='PUBLISHED', remote_id='ig-media-1', error=None, attempts=1,
        created_at='2026-08-13T00:00:00+00:00', updated_at='2026-08-13T00:01:00+00:00', render_id=None,
    )
    payload.update(changes)
    return Publication(**payload)


def paid_draft():
    return PaidMediaDraft(
        id='draft-1', project_id='project-1', ad_account_id='77', campaign_name='Campaign',
        campaign_objective='OUTCOME_TRAFFIC', special_ad_categories=[], adset_name='Ad Set', daily_budget=2100,
        optimization_goal='LINK_CLICKS', targeting={'geo_locations': {'countries': ['CO']}}, page_id='page-1',
        instagram_actor_id='ig-1', creative_name='Creative', message='Message', link_url='https://example.com',
        picture_url='https://cdn.example.com/a.jpg', call_to_action='LEARN_MORE', ad_name='Ad', status='REMOTE_PAUSED',
        campaign_id='campaign-1', adset_id='adset-1', creative_id='creative-1', ad_id='ad-1',
        created_at='2026-08-13T00:00:00+00:00', updated_at='2026-08-13T00:01:00+00:00',
    )


class MetaObservabilityTests(unittest.TestCase):
    def client(self, transport):
        return MetaGraphClient('user-secret', 'v25.0', transport=transport)

    def test_instagram_publication_returns_metadata_and_metrics_without_token_echo(self):
        transport = FakeTransport()
        result = MetaObservability(self.client(transport)).publication(publication())
        self.assertTrue(result['available'])
        self.assertEqual(result['remote']['media_product_type'], 'REELS')
        self.assertEqual(result['insights']['reach'], 1)
        self.assertEqual(result['insights']['total_interactions'], 7)
        self.assertNotIn('secret', str(result).lower())
        self.assertTrue(all(call[0] == 'GET' for call in transport.calls))
        insight_call = next(call for call in transport.calls if call[1].endswith('/ig-media-1/insights'))
        self.assertEqual(insight_call[2]['access_token'], 'page-secret')

    def test_facebook_reel_uses_official_status_readback(self):
        transport = FakeTransport()
        row = publication(channel='facebook_page', target_id='page-1', target_name='Page One', remote_id='fb-reel-1', media_url=None, render_id='render-1')
        result = MetaObservability(self.client(transport)).publication(row)
        self.assertTrue(result['available'])
        self.assertEqual(result['remote_state'], 'READY')
        status_call = next(call for call in transport.calls if call[1].endswith('/fb-reel-1'))
        self.assertEqual(status_call[2]['fields'], 'status')
        self.assertEqual(status_call[2]['access_token'], 'page-secret')

    def test_paid_media_observability_is_get_only_and_confirms_paused_hierarchy(self):
        transport = FakeTransport()
        result = MetaObservability(self.client(transport)).paid_media(paid_draft(), date_preset='maximum')
        self.assertTrue(result['available'])
        self.assertEqual(result['objects']['campaign']['observed_state'], 'PAUSED')
        self.assertEqual(result['insights']['impressions'], '120')
        self.assertTrue(result['safety']['configured_paused'])
        self.assertFalse(result['safety']['explicit_active_detected'])
        self.assertFalse(result['safety']['activation_endpoint_present'])
        self.assertTrue(all(method == 'GET' for method, _, _ in transport.calls))
        insights_call = next(call for call in transport.calls if call[1].endswith('/ad-1/insights'))
        self.assertEqual(insights_call[2]['date_preset'], 'maximum')

    def test_remote_active_state_is_reported_as_safety_failure(self):
        result = MetaObservability(self.client(FakeTransport(active_ad=True))).paid_media(paid_draft())
        self.assertTrue(result['safety']['explicit_active_detected'])
        self.assertFalse(result['safety']['configured_paused'])

    def test_invalid_date_preset_fails_before_network(self):
        transport = FakeTransport()
        with self.assertRaises(ValueError):
            MetaObservability(self.client(transport)).paid_media(paid_draft(), date_preset='arbitrary')
        self.assertEqual(transport.calls, [])


if __name__ == '__main__':
    unittest.main()
