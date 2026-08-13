import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave27 import AppRuntime, create_server
from binario_marketing.wave27_instagram_local import Wave27SocialScheduler, Wave27SocialStore


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


class InstagramLocalHttpApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / 'data')
        self.server = create_server(self.runtime, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_address[1]}'
        self.project_id = self.runtime.create_project('Instagram local')['id']

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_wave27_runtime_installs_specialized_store_and_scheduler(self):
        self.assertIsInstance(self.runtime.social, Wave27SocialStore)
        self.assertIsInstance(self.runtime.social_scheduler, Wave27SocialScheduler)

    def test_wave27_browser_bundle_is_served_by_specialized_handler(self):
        with urlopen(f'{self.base}/instagram-local-reel.js', timeout=5) as response:
            body = response.read().decode('utf-8')
        self.assertEqual(response.status, 200)
        self.assertIn('Origen del Reel', body)
        self.assertIn('Render local certificado', body)
        self.assertIn('createInstagramLocalPublication', body)

    def test_http_accepts_local_instagram_reel_intent_without_public_url(self):
        status, row = request_json(
            f'{self.base}/api/projects/{self.project_id}/publications',
            method='POST',
            payload={
                'channel': 'instagram',
                'target_id': 'ig-1',
                'target_name': '@brand',
                'kind': 'reel',
                'message': 'Reel local',
                'render_id': 'render-1',
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(row['status'], 'DRAFT')
        self.assertEqual(row['render_id'], 'render-1')
        self.assertIsNone(row['media_url'])

        _, detail = request_json(f'{self.base}/api/projects/{self.project_id}')
        stored = next(item for item in detail['publications'] if item['id'] == row['id'])
        self.assertEqual(stored['render_id'], 'render-1')
        self.assertIsNone(stored['media_url'])

    def test_http_rejects_ambiguous_instagram_reel_source(self):
        request = Request(
            f'{self.base}/api/projects/{self.project_id}/publications',
            data=json.dumps({
                'channel': 'instagram',
                'target_id': 'ig-1',
                'kind': 'reel',
                'message': 'Ambiguo',
                'render_id': 'render-1',
                'media_url': 'https://cdn.example/reel.mp4',
            }).encode('utf-8'),
            method='POST',
            headers={'Content-Type': 'application/json'},
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 400)
        body = json.loads(raised.exception.read().decode('utf-8'))
        self.assertIn('exactly one', body['error'])

    def test_existing_facebook_create_contract_still_delegates_to_base_store(self):
        status, row = request_json(
            f'{self.base}/api/projects/{self.project_id}/publications',
            method='POST',
            payload={
                'channel': 'facebook_page',
                'target_id': 'page-1',
                'kind': 'text',
                'message': 'Sin regresión',
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(row['channel'], 'facebook_page')
        self.assertEqual(row['kind'], 'text')


if __name__ == '__main__':
    unittest.main()
