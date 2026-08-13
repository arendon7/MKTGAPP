import tempfile
import unittest
from pathlib import Path

from binario_marketing.service_wave27 import AppRuntime


ROOT = Path(__file__).resolve().parents[1]


class InstagramLocalPublishNowContractTests(unittest.TestCase):
    def test_local_publish_failure_is_persisted_and_raised_to_caller(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / 'data')
            try:
                runtime.social_scheduler.client_factory = lambda: object()
                project_id = runtime.create_project('Publish contract')['id']
                row = runtime.create_publication(project_id, {
                    'channel': 'instagram',
                    'target_id': 'ig-1',
                    'target_name': '@brand',
                    'kind': 'reel',
                    'message': 'Contract test',
                    'render_id': 'missing-render',
                })
                with self.assertRaisesRegex(ValueError, 'render registry is unavailable'):
                    runtime.publish_publication_now(project_id, row['id'])
                stored = runtime.social.get(row['id'])
                self.assertEqual(stored.status, 'FAILED')
                self.assertIn('render registry is unavailable', stored.error)
            finally:
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()


if __name__ == '__main__':
    unittest.main()
