import unittest

from binario_marketing.meta_ads import (
    LinkCreativeSpec,
    MetaAdsBuilder,
    PausedAdSetSpec,
    PausedAdSpec,
)
from binario_marketing.meta_graph import MetaGraphClient


class FakeAdsTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        if url.endswith('/act_77/adsets'):
            return {'id': 'adset-1'}
        if url.endswith('/act_77/adcreatives'):
            return {'id': 'creative-1'}
        if url.endswith('/act_77/ads'):
            return {'id': 'ad-1'}
        raise AssertionError(f'unexpected request {method} {url}')


class MetaAdsBuilderTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeAdsTransport()
        self.builder = MetaAdsBuilder(MetaGraphClient('token', 'v25.0', transport=self.fake))

    def test_adset_is_forced_paused_with_budget_and_targeting(self):
        remote_id = self.builder.create_paused_adset(PausedAdSetSpec(
            ad_account_id='act_77',
            campaign_id='campaign-1',
            name='Colombia tráfico',
            daily_budget=2100,
            optimization_goal='LINK_CLICKS',
            targeting={'age_min': 21, 'age_max': 55, 'geo_locations': {'countries': ['CO']}},
        ))
        self.assertEqual(remote_id, 'adset-1')
        call = self.fake.calls[-1]
        self.assertEqual(call[2]['status'], 'PAUSED')
        self.assertEqual(call[2]['daily_budget'], '2100')
        self.assertIn('"countries":["CO"]', call[2]['targeting'])

    def test_link_creative_uses_page_story_without_activation_state(self):
        remote_id = self.builder.create_link_creative(LinkCreativeSpec(
            ad_account_id='77',
            page_id='page-1',
            instagram_actor_id='ig-1',
            name='Creative prueba',
            message='Transformar residuos en vida',
            link_url='https://example.com/producto',
            picture_url='https://cdn.example.com/producto.jpg',
            call_to_action='LEARN_MORE',
        ))
        self.assertEqual(remote_id, 'creative-1')
        params = self.fake.calls[-1][2]
        self.assertNotIn('status', params)
        story = params['object_story_spec']
        self.assertIn('"page_id":"page-1"', story)
        self.assertIn('"instagram_actor_id":"ig-1"', story)
        self.assertIn('"type":"LEARN_MORE"', story)

    def test_ad_is_forced_paused_and_references_existing_creative(self):
        remote_id = self.builder.create_paused_ad(PausedAdSpec(
            ad_account_id='77',
            adset_id='adset-1',
            creative_id='creative-1',
            name='Ad prueba',
        ))
        self.assertEqual(remote_id, 'ad-1')
        params = self.fake.calls[-1][2]
        self.assertEqual(params['status'], 'PAUSED')
        self.assertIn('"creative_id":"creative-1"', params['creative'])

    def test_invalid_budget_targeting_url_and_active_state_have_no_escape_hatch(self):
        with self.assertRaises(ValueError):
            PausedAdSetSpec('77', 'campaign-1', 'Bad', 0, 'LINK_CLICKS', {'geo_locations': {'countries': ['CO']}}).validate()
        with self.assertRaises(ValueError):
            PausedAdSetSpec('77', 'campaign-1', 'Bad', 1000, 'LINK_CLICKS', {}).validate()
        with self.assertRaises(ValueError):
            LinkCreativeSpec('77', 'page-1', 'Bad', 'copy', 'http://example.com', 'https://cdn.example.com/a.jpg').validate()
        source = __import__('pathlib').Path(__file__).resolve().parents[1] / 'src' / 'binario_marketing' / 'meta_ads.py'
        text = source.read_text(encoding='utf-8')
        self.assertNotIn('status": "ACTIVE"', text)
        self.assertNotIn("status': 'ACTIVE'", text)


if __name__ == '__main__':
    unittest.main()
