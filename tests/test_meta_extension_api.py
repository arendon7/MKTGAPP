import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.meta_graph import MetaGraphError
from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def request_json(url, *, method='GET', payload=None):
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    request = Request(url, data=data, method=method, headers=headers)
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode('utf-8'))


class MetaExtensionApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / 'data')
        self.server = create_server(self.runtime, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.project_id = self.runtime.create_project('Paid Media')['id']
        self.paid_payload = {
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
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_meta_connection_validates_and_writes_secret_without_returning_it(self):
        token = 'secret-meta-token'
        credential = SimpleNamespace(configured=True, source='keychain', writable=True)
        fake_client = SimpleNamespace(identity=lambda: {'id': 'user-1', 'name': 'Meta User'})
        with patch('binario_marketing.service.MetaGraphClient', return_value=fake_client) as client_cls, \
             patch('binario_marketing.service.MetaCredentialStore') as store_cls, \
             patch.object(self.runtime, 'meta_status', return_value={'configured': True, 'credential_source': 'keychain', 'scheduler': {'running': True}}):
            store_cls.return_value.write.return_value = credential
            status, payload = request_json(
                f'{self.base}/api/meta/connection',
                method='POST',
                payload={'access_token': token},
            )
        self.assertEqual(status, 201)
        client_cls.assert_called_once()
        store_cls.return_value.write.assert_called_once_with(token)
        self.assertEqual(payload['identity']['id'], 'user-1')
        self.assertNotIn(token, json.dumps(payload))
        timeline = [entry.__dict__ for entry in self.runtime.workspace.registries.timeline.entries()]
        self.assertFalse(any(token in json.dumps(entry) for entry in timeline))

    def test_meta_disconnect_removes_keychain_connection_without_secret_echo(self):
        current = SimpleNamespace(configured=True, source='keychain', writable=True)
        deleted = SimpleNamespace(configured=False, source='none', writable=True)
        with patch('binario_marketing.service.MetaCredentialStore') as store_cls, \
             patch.object(self.runtime, 'meta_status', return_value={'configured': False, 'credential_source': 'none', 'scheduler': {'running': False}}):
            store_cls.return_value.status.return_value = current
            store_cls.return_value.delete.return_value = deleted
            status, payload = request_json(f'{self.base}/api/meta/connection', method='DELETE')
        self.assertEqual(status, 200)
        store_cls.return_value.delete.assert_called_once_with()
        self.assertFalse(payload['configured'])
        self.assertNotIn('token', json.dumps(payload).lower())
        timeline = [entry.__dict__ for entry in self.runtime.workspace.registries.timeline.entries()]
        self.assertTrue(any(entry['kind'] == 'meta.disconnected' for entry in timeline))

    def test_paid_media_draft_http_round_trip_and_project_detail(self):
        status, row = request_json(
            f'{self.base}/api/projects/{self.project_id}/paid-media',
            method='POST',
            payload=self.paid_payload,
        )
        self.assertEqual(status, 201)
        self.assertEqual(row['status'], 'DRAFT')
        draft_id = row['id']
        status, rows = request_json(f'{self.base}/api/projects/{self.project_id}/paid-media')
        self.assertEqual(status, 200)
        self.assertEqual([item['id'] for item in rows], [draft_id])
        status, detail = request_json(f'{self.base}/api/projects/{self.project_id}')
        self.assertEqual(status, 200)
        self.assertEqual(detail['paid_media'][0]['id'], draft_id)
        status, cancelled = request_json(
            f'{self.base}/api/projects/{self.project_id}/paid-media/{draft_id}',
            method='DELETE',
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled['status'], 'CANCELLED')

    def test_paid_media_draft_cannot_be_mutated_through_another_project(self):
        _, row = request_json(
            f'{self.base}/api/projects/{self.project_id}/paid-media',
            method='POST',
            payload=self.paid_payload,
        )
        other_id = self.runtime.create_project('Other paid-media project')['id']
        request = Request(
            f'{self.base}/api/projects/{other_id}/paid-media/{row["id"]}',
            method='DELETE',
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 404)
        persisted = self.runtime.paid_media.get(row['id'])
        self.assertEqual(persisted.status, 'DRAFT')
        self.assertEqual(persisted.project_id, self.project_id)

    def test_remote_paused_creation_resumes_after_confirmed_campaign_checkpoint(self):
        _, draft = request_json(
            f'{self.base}/api/projects/{self.project_id}/paid-media',
            method='POST',
            payload=self.paid_payload,
        )
        draft_id = draft['id']
        client = SimpleNamespace(create_paused_campaign=lambda *args, **kwargs: 'campaign-1')
        builder = SimpleNamespace(
            create_paused_adset=lambda spec: (_ for _ in ()).throw(MetaGraphError('simulated adset failure')),
            create_link_creative=lambda spec: 'creative-1',
            create_paused_ad=lambda spec: 'ad-1',
        )
        with patch('binario_marketing.service.MetaGraphClient.from_env', return_value=client), \
             patch('binario_marketing.service.MetaAdsBuilder', return_value=builder):
            request = Request(
                f'{self.base}/api/projects/{self.project_id}/paid-media/{draft_id}/create-paused',
                data=b'{}', method='POST', headers={'Content-Type': 'application/json'},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 502)
        checkpoint = self.runtime.paid_media.get(draft_id)
        self.assertEqual(checkpoint.campaign_id, 'campaign-1')
        self.assertIsNone(checkpoint.adset_id)

        class NoDuplicateCampaignClient:
            def create_paused_campaign(self, *args, **kwargs):
                raise AssertionError('campaign must not be created twice after checkpoint')

        builder2 = SimpleNamespace(
            create_paused_adset=lambda spec: 'adset-1',
            create_link_creative=lambda spec: 'creative-1',
            create_paused_ad=lambda spec: 'ad-1',
        )
        with patch('binario_marketing.service.MetaGraphClient.from_env', return_value=NoDuplicateCampaignClient()), \
             patch('binario_marketing.service.MetaAdsBuilder', return_value=builder2):
            status, result = request_json(
                f'{self.base}/api/projects/{self.project_id}/paid-media/{draft_id}/create-paused',
                method='POST', payload={},
            )
        self.assertEqual(status, 201)
        self.assertEqual(result['status'], 'REMOTE_PAUSED')
        self.assertEqual(result['campaign_id'], 'campaign-1')
        self.assertEqual(result['adset_id'], 'adset-1')
        self.assertEqual(result['creative_id'], 'creative-1')
        self.assertEqual(result['ad_id'], 'ad-1')

    def test_paid_media_http_rejects_secret_fields(self):
        request = Request(
            f'{self.base}/api/projects/{self.project_id}/paid-media',
            data=json.dumps(dict(self.paid_payload, access_token='never-persist')).encode('utf-8'),
            method='POST', headers={'Content-Type': 'application/json'},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 400)
        body = json.loads(raised.exception.read().decode('utf-8'))
        self.assertIn('credentials must not be persisted', body['error'])


if __name__ == '__main__':
    unittest.main()
