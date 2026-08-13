import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class MetaDiagnosticsApiTests(unittest.TestCase):
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

    def test_diagnostics_route_is_get_only_and_secret_free(self):
        report = {
            'status': 'PASS', 'graph_version': 'v25.0', 'credential_source': 'keychain',
            'identity': {'id': '1', 'name': 'UAT'}, 'permissions': {'available': True, 'missing': {}},
            'pages': [], 'ad_accounts': [], 'ready': {'facebook_publish': True}, 'checks': [],
            'security': {'token_included': False, 'mutation_performed': False},
        }
        fake = type('D', (), {'report': lambda self: report})()
        with patch('binario_marketing.service.MetaDiagnostics.from_env', return_value=fake):
            with urlopen(f'{self.base}/api/meta/diagnostics', timeout=5) as response:
                payload = json.loads(response.read().decode('utf-8'))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload['status'], 'PASS')
        self.assertNotIn('access_token', json.dumps(payload).lower())

        request = Request(f'{self.base}/api/meta/diagnostics', data=b'{}', method='POST', headers={'Content-Type': 'application/json'})
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 404)

    def test_diagnostics_static_assets_are_served_by_local_runtime(self):
        with urlopen(f'{self.base}/meta-diagnostics.js', timeout=5) as response:
            js = response.read().decode('utf-8')
        with urlopen(f'{self.base}/meta-diagnostics.css', timeout=5) as response:
            css = response.read().decode('utf-8')
        self.assertIn('runMetaDiagnostics', js)
        self.assertIn('/api/meta/diagnostics', js)
        self.assertIn('reporte sin token', js)
        self.assertIn('.meta-diagnostics-panel', css)


if __name__ == '__main__':
    unittest.main()
