import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class MetaReadinessApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / 'data')
        self.server = create_server(self.runtime, '127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _get(self, path):
        with urlopen(f'{self.base}{path}', timeout=5) as response:
            return response.status, json.loads(response.read().decode('utf-8'))

    def test_disconnected_readiness_is_safe_and_explicit(self):
        with patch.object(self.runtime, 'meta_status', return_value={'configured': False}):
            status, payload = self._get('/api/meta/readiness')
        self.assertEqual(status, 200)
        self.assertFalse(payload['configured'])
        self.assertFalse(payload['facebook']['ready'])
        self.assertFalse(payload['instagram']['ready'])
        self.assertFalse(payload['ads']['ready'])
        self.assertIn('meta_not_connected', payload['facebook']['reasons'])

    def test_connected_readiness_passes_through_sanitized_diagnostics(self):
        diagnostic = {
            'permissions': [{'name': 'instagram_content_publish', 'status': 'granted'}],
            'facebook': {'ready': True, 'reasons': [], 'pages': [{'id': 'page-1'}]},
            'instagram': {'ready': True, 'reasons': [], 'accounts': [{'id': 'ig-1'}], 'missing_permissions': []},
            'ads': {'ready': False, 'reasons': ['ads_management'], 'accounts': [], 'missing_permissions': ['ads_management']},
        }
        with patch.object(self.runtime, 'meta_status', return_value={'configured': True}), \
             patch('binario_marketing.service.MetaGraphClient.from_env', return_value=object()), \
             patch('binario_marketing.service.MetaReadinessService') as readiness_cls:
            readiness_cls.return_value.diagnose.return_value = diagnostic
            status, payload = self._get('/api/meta/readiness')
        self.assertEqual(status, 200)
        self.assertTrue(payload['configured'])
        self.assertTrue(payload['facebook']['ready'])
        self.assertTrue(payload['instagram']['ready'])
        self.assertFalse(payload['ads']['ready'])
        self.assertNotIn('access_token', json.dumps(payload).lower())
        self.assertNotIn('token', payload)


if __name__ == '__main__':
    unittest.main()
