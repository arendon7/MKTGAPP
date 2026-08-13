import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class MetaReadinessUiContractTests(unittest.TestCase):
    def test_readiness_bundle_has_three_independent_channels_and_missing_permission_copy(self):
        js = (ROOT / 'web' / 'meta-readiness.js').read_text(encoding='utf-8')
        for token in (
            '/api/meta/readiness',
            "readinessRow('Facebook'",
            "readinessRow('Instagram'",
            "readinessRow('Ads'",
            'instagram_content_publish',
            'pages_show_list',
            'ads_management',
            'page_access_token_unavailable',
            'LISTO',
            'PENDIENTE',
        ):
            self.assertIn(token, js)
        self.assertNotIn('localStorage', js)
        self.assertNotIn('sessionStorage', js)
        self.assertNotIn('META_ACCESS_TOKEN', js)
        self.assertNotIn('Authorization:', js)
        self.assertNotIn('Bearer ', js)
        self.assertNotIn('meta-token-input', js)

    def test_service_composes_existing_social_bundle_with_readiness_module(self):
        service = (ROOT / 'src' / 'binario_marketing' / 'service.py').read_text(encoding='utf-8')
        self.assertIn('def _social_bundle(self)', service)
        self.assertIn('social = root / "social.js"', service)
        self.assertIn('readiness = root / "meta-readiness.js"', service)
        self.assertIn('social.read_bytes() + b"\\n" + readiness.read_bytes()', service)
        self.assertIn('["api", "meta", "readiness"]', service)

    def test_local_http_social_bundle_contains_wave23_and_wave24_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / 'data')
            server = create_server(runtime, '127.0.0.1', 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(f'{base}/social.js', timeout=5) as response:
                    body = response.read().decode('utf-8')
                    status = response.status
                self.assertEqual(status, 200)
                self.assertIn('Meta, publicaciones y pauta', body)
                self.assertIn('meta-readiness-panel', body)
                self.assertIn('/api/meta/readiness', body)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()


if __name__ == '__main__':
    unittest.main()
