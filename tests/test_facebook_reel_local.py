import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.social_service import MetaSocialPublisher
from binario_marketing.social_store import SocialStore


class FakeGraph:
    def __init__(self):
        self.calls = []
        self.binary_calls = []

    def transport(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        if url.endswith('/me/accounts'):
            return {'data': [{'id': 'page-1', 'name': 'Greenatics', 'access_token': 'page-secret'}]}
        if url.endswith('/me/video_reels') and params.get('upload_phase') == 'start':
            return {'video_id': 'reel-900', 'upload_url': 'https://rupload.facebook.com/video-upload/v25.0/reel-900'}
        if url.endswith('/me/video_reels') and params.get('upload_phase') == 'finish':
            if params.get('video_state') != 'PUBLISHED':
                raise AssertionError('Facebook Reel must finish as PUBLISHED')
            return {'success': True}
        raise AssertionError(f'unexpected request: {method} {url} {params}')

    def binary(self, upload_url, file_path, access_token):
        path = Path(file_path)
        self.binary_calls.append((upload_url, path, access_token, path.read_bytes()))
        if access_token != 'page-secret':
            raise AssertionError('binary upload did not use Page token')
        return {'success': True}


class FacebookReelClientTests(unittest.TestCase):
    def test_client_initializes_streams_and_finishes_local_reel(self):
        fake = FakeGraph()
        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / 'reel.mp4'
            video.write_bytes(b'certified-video-bytes')
            client = MetaGraphClient('user-secret', 'v25.0', transport=fake.transport, binary_transport=fake.binary)
            remote_id = client.publish_page_reel_local('page-1', video, 'Caption')
        self.assertEqual(remote_id, 'reel-900')
        self.assertEqual(len(fake.binary_calls), 1)
        upload_url, _, token, body = fake.binary_calls[0]
        self.assertTrue(upload_url.startswith('https://rupload.facebook.com/'))
        self.assertEqual(token, 'page-secret')
        self.assertEqual(body, b'certified-video-bytes')
        finish = [call for call in fake.calls if call[2].get('upload_phase') == 'finish'][0]
        self.assertEqual(finish[2]['video_id'], 'reel-900')
        self.assertEqual(finish[2]['description'], 'Caption')


class ManagedFacebookReelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.social_root = self.data / 'State' / 'social'
        self.render_root = self.data / 'State' / 'renders'
        self.projects_root = self.data / 'Projects'
        self.render_root.mkdir(parents=True)
        self.projects_root.mkdir(parents=True)
        self.store = SocialStore(self.social_root)
        self.project_id = 'project-1'
        self.directory = 'demo-project-1'
        self.export = self.projects_root / self.directory / 'exports' / 'reel.mp4'
        self.export.parent.mkdir(parents=True)
        self.export.write_bytes(b'local-facebook-reel')
        (self.projects_root / 'projects.json').write_text(json.dumps([{
            'id': self.project_id,
            'name': 'Demo',
            'directory': self.directory,
            'created_at': '2026-08-12T00:00:00+00:00',
        }]), encoding='utf-8')
        self.render = {
            'id': 'render-1',
            'project_id': self.project_id,
            'status': 'PASS',
            'width': 1080,
            'height': 1920,
            'start': 0.0,
            'end': 10.0,
            'output_name': 'reel.mp4',
            'bytes': self.export.stat().st_size,
        }
        self._write_renders()
        self.fake = FakeGraph()
        self.client = MetaGraphClient('user-secret', 'v25.0', transport=self.fake.transport, binary_transport=self.fake.binary)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_renders(self):
        (self.render_root / 'jobs.json').write_text(json.dumps([self.render]), encoding='utf-8')

    def _publication(self):
        row = self.store.create(self.project_id, {
            'channel': 'facebook_page',
            'target_id': 'page-1',
            'target_name': 'Greenatics',
            'kind': 'reel',
            'message': 'Reel desde render local',
            'render_id': 'render-1',
        })
        return self.store.queue(row.id)

    def test_publisher_resolves_certified_managed_render_without_persisting_path(self):
        row = self._publication()
        persisted = json.loads((self.social_root / f'{row.id}.json').read_text(encoding='utf-8'))
        self.assertEqual(persisted['render_id'], 'render-1')
        self.assertNotIn(str(self.export), json.dumps(persisted))
        result = MetaSocialPublisher(self.store, self.client).publish(row.id)
        self.assertEqual(result.status, 'PUBLISHED')
        self.assertEqual(result.remote_id, 'reel-900')
        self.assertEqual(self.fake.binary_calls[0][1], self.export.resolve())

    def test_tampered_render_is_rejected_before_meta_binary_upload(self):
        row = self._publication()
        self.export.write_bytes(b'changed-after-certification')
        result = MetaSocialPublisher(self.store, self.client).publish(row.id)
        self.assertEqual(result.status, 'FAILED')
        self.assertIn('size no longer matches', result.error)
        self.assertEqual(self.fake.binary_calls, [])

    def test_wrong_aspect_or_duration_is_rejected(self):
        for width, height, end, expected in (
            (1920, 1080, 10.0, 'must be 9:16'),
            (1080, 1920, 2.0, 'between 4 and 60'),
            (1080, 1920, 61.0, 'between 4 and 60'),
        ):
            with self.subTest(width=width, height=height, end=end):
                self.render.update(width=width, height=height, end=end)
                self._write_renders()
                row = self._publication()
                result = MetaSocialPublisher(self.store, self.client).publish(row.id)
                self.assertEqual(result.status, 'FAILED')
                self.assertIn(expected, result.error)

    def test_store_requires_render_reference_for_facebook_reel(self):
        with self.assertRaisesRegex(ValueError, 'render_id'):
            self.store.create(self.project_id, {
                'channel': 'facebook_page',
                'target_id': 'page-1',
                'kind': 'reel',
                'message': 'Sin render',
            })


class FacebookReelUiContractTests(unittest.TestCase):
    def test_ui_selects_only_pass_vertical_four_to_sixty_second_renders(self):
        root = Path(__file__).resolve().parents[1]
        js = (root / 'web' / 'social.js').read_text(encoding='utf-8')
        for token in ('Reel local', 'social-render-id', 'render_id:renderId', "row.status==='PASS'", 'Number(row.width)*16===Number(row.height)*9', '>=4', '<=60'):
            self.assertIn(token, js)
        self.assertIn('Instagram local seguirá bloqueado', js)


if __name__ == '__main__':
    unittest.main()
