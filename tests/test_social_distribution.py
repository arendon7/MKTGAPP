import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.social_service import MetaSocialPublisher
from binario_marketing.social_store import SocialStore


class FakeMeta:
    def __init__(self):
        self.calls = []

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        if url.endswith('/me/accounts'):
            return {
                'data': [{
                    'id': 'page-1',
                    'name': 'Greenatics',
                    'access_token': 'page-secret',
                    'instagram_business_account': {'id': 'ig-1', 'username': 'greenatics'},
                }]
            }
        if url.endswith('/me/adaccounts'):
            return {'data': [{'id': 'act_77', 'account_id': '77', 'name': 'Ads', 'account_status': 1, 'currency': 'COP', 'timezone_name': 'America/Bogota'}]}
        if url.endswith('/page-1/feed'):
            self.assert_token(params, 'page-secret')
            return {'id': 'page-1_900'}
        if url.endswith('/page-1/photos'):
            self.assert_token(params, 'page-secret')
            return {'post_id': 'page-1_901'}
        if url.endswith('/ig-1/media'):
            self.assert_token(params, 'page-secret')
            return {'id': 'container-1'}
        if url.endswith('/container-1'):
            self.assert_token(params, 'page-secret')
            return {'status_code': 'FINISHED'}
        if url.endswith('/ig-1/media_publish'):
            self.assert_token(params, 'page-secret')
            return {'id': 'ig-media-1'}
        if url.endswith('/act_77/campaigns'):
            return {'id': 'campaign-1'}
        raise AssertionError(f'unexpected Meta request: {method} {url}')

    @staticmethod
    def assert_token(params, expected):
        if params.get('access_token') != expected:
            raise AssertionError(f'expected provider token {expected!r}, got {params.get("access_token")!r}')


class SocialStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SocialStore(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_credentials_are_rejected_from_durable_publication_state(self):
        with self.assertRaisesRegex(ValueError, 'credentials must not be persisted'):
            self.store.create('project-1', {
                'channel': 'facebook_page',
                'target_id': 'page-1',
                'kind': 'text',
                'message': 'Hola',
                'access_token': 'never-write-me',
            })

    def test_draft_queue_due_and_terminal_publication_lifecycle(self):
        row = self.store.create('project-1', {
            'channel': 'facebook_page',
            'target_id': 'page-1',
            'target_name': 'Greenatics',
            'kind': 'text',
            'message': 'Transformar residuos en vida',
        })
        self.assertEqual(row.status, 'DRAFT')
        when = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        row = self.store.queue(row.id, when)
        self.assertEqual(row.status, 'QUEUED')
        self.assertEqual([item.id for item in self.store.due()], [row.id])
        row = self.store.transition(row.id, 'PUBLISHING')
        self.assertEqual(row.attempts, 1)
        row = self.store.transition(row.id, 'PUBLISHED', remote_id='remote-1')
        self.assertEqual(row.status, 'PUBLISHED')
        self.assertEqual(row.remote_id, 'remote-1')
        with self.assertRaises(ValueError):
            self.store.transition(row.id, 'QUEUED')

    def test_instagram_media_cannot_pretend_a_local_file_is_public(self):
        with self.assertRaisesRegex(ValueError, 'public media_url'):
            self.store.create('project-1', {
                'channel': 'instagram',
                'target_id': 'ig-1',
                'kind': 'reel',
                'message': 'Clip listo',
                'asset_id': 'local-render-id',
            })


class MetaGraphContractTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeMeta()
        self.client = MetaGraphClient('user-secret', 'v25.0', transport=self.fake)

    def test_page_discovery_is_sanitized_and_linked_instagram_is_exposed(self):
        pages = self.client.pages()
        self.assertEqual(pages[0]['id'], 'page-1')
        self.assertEqual(pages[0]['instagram']['id'], 'ig-1')
        self.assertNotIn('access_token', pages[0])
        self.assertTrue(pages[0]['page_token_available'])

    def test_facebook_publication_resolves_page_token_only_in_memory(self):
        remote_id = self.client.publish_page_feed('page-1', 'Hola Meta', 'https://example.com')
        self.assertEqual(remote_id, 'page-1_900')
        post = [call for call in self.fake.calls if call[1].endswith('/page-1/feed')][-1]
        self.assertEqual(post[2]['access_token'], 'page-secret')
        self.assertEqual(post[2]['link'], 'https://example.com')

    def test_instagram_reel_uses_linked_page_token(self):
        container = self.client.create_instagram_container('ig-1', 'https://cdn.example.com/reel.mp4', 'Hola', 'reel')
        self.assertEqual(container, 'container-1')
        self.assertEqual(self.client.instagram_container_status(container, 'ig-1'), 'FINISHED')
        self.assertEqual(self.client.publish_instagram_container('ig-1', container), 'ig-media-1')

    def test_marketing_campaign_is_forced_paused(self):
        remote_id = self.client.create_paused_campaign('act_77', name='Prueba controlada', objective='OUTCOME_TRAFFIC')
        self.assertEqual(remote_id, 'campaign-1')
        call = [item for item in self.fake.calls if item[1].endswith('/act_77/campaigns')][-1]
        self.assertEqual(call[2]['status'], 'PAUSED')
        self.assertEqual(call[2]['special_ad_categories'], '[]')


class SocialPublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = SocialStore(Path(self.tmp.name))
        self.fake = FakeMeta()
        self.client = MetaGraphClient('user-secret', 'v25.0', transport=self.fake)
        self.publisher = MetaSocialPublisher(self.store, self.client, sleep=lambda _: None, reel_poll_interval=0)

    def tearDown(self):
        self.tmp.cleanup()

    def test_due_facebook_post_runs_to_published(self):
        row = self.store.create('project-1', {
            'channel': 'facebook_page',
            'target_id': 'page-1',
            'kind': 'text',
            'message': 'Publicación automática',
            'scheduled_for': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        })
        result = self.publisher.run_due()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['status'], 'PUBLISHED')
        self.assertEqual(result[0]['remote_id'], 'page-1_900')
        self.assertEqual(self.store.get(row.id).attempts, 1)

    def test_due_instagram_reel_waits_for_container_then_publishes(self):
        row = self.store.create('project-1', {
            'channel': 'instagram',
            'target_id': 'ig-1',
            'kind': 'reel',
            'message': 'Reel automático',
            'media_url': 'https://cdn.example.com/reel.mp4',
            'scheduled_for': (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
        })
        result = self.publisher.run_due()
        self.assertEqual(result[0]['status'], 'PUBLISHED')
        self.assertEqual(result[0]['remote_id'], 'ig-media-1')
        self.assertEqual(self.store.get(row.id).status, 'PUBLISHED')


if __name__ == '__main__':
    unittest.main()
