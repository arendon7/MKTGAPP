import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.meta_graph import MetaGraphClient, MetaGraphError
from binario_marketing.meta_instagram_local import InstagramLocalReelUploader
from binario_marketing.wave27_instagram_local import (
    Wave27MetaSocialPublisher,
    Wave27SocialStore,
    instagram_managed_render_path,
)


class FakeMetaTransport:
    def __init__(self, upload_host='rupload.facebook.com'):
        self.calls = []
        self.local_status_calls = 0
        self.upload_host = upload_host

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        path = url.split('/v25.0/', 1)[-1]
        if path == 'me/accounts':
            return {'data': [{'id': 'page-1', 'name': 'Page', 'access_token': 'page-credential', 'instagram_business_account': {'id': 'ig-1', 'username': 'brand'}}]}
        if path == 'ig-1/media' and params.get('upload_type') == 'resumable':
            return {'id': 'container-local', 'uri': f'https://{self.upload_host}/ig-api-upload/v25.0/container-local'}
        if path == 'ig-1/media' and params.get('video_url'):
            return {'id': 'container-url'}
        if path == 'container-local':
            self.local_status_calls += 1
            if self.local_status_calls == 1:
                return {'id': 'container-local', 'status_code': 'IN_PROGRESS', 'video_status': {'uploading_phase': {'status': 'complete'}, 'processing_phase': {'status': 'in_progress'}}}
            return {'id': 'container-local', 'status_code': 'FINISHED', 'status': 'Finished'}
        if path == 'container-url':
            return {'id': 'container-url', 'status_code': 'FINISHED', 'status': 'Finished'}
        if path == 'ig-1/media_publish':
            return {'id': 'ig-media-local' if params.get('creation_id') == 'container-local' else 'ig-media-url'}
        raise AssertionError(f'unexpected Meta path: {path}')


class FakeBinaryTransport:
    def __init__(self):
        self.calls = []

    def __call__(self, upload_url, file_path, credential):
        self.calls.append((upload_url, Path(file_path), credential))
        return {'success': True}


def local_payload(**changes):
    payload = {
        'channel': 'instagram',
        'target_id': 'ig-1',
        'target_name': '@brand',
        'kind': 'reel',
        'message': 'Local Reel',
        'render_id': 'render-1',
    }
    payload.update(changes)
    return payload


class InstagramLocalReelTests(unittest.TestCase):
    def test_store_accepts_exactly_one_instagram_reel_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Wave27SocialStore(Path(tmp))
            local = store.create('project-1', local_payload())
            self.assertEqual(local.render_id, 'render-1')
            self.assertIsNone(local.media_url)

            hosted = store.create('project-1', local_payload(render_id=None, media_url='https://cdn.example/reel.mp4'))
            self.assertIsNone(hosted.render_id)
            self.assertEqual(hosted.media_url, 'https://cdn.example/reel.mp4')

            with self.assertRaisesRegex(ValueError, 'exactly one'):
                store.create('project-1', local_payload(media_url='https://cdn.example/reel.mp4'))
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                store.create('project-1', local_payload(render_id=None))

    def test_resumable_flow_uses_user_credential_in_memory_and_rupload_uri(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / 'reel.mp4'
            media.write_bytes(b'local-instagram-reel')
            store = Wave27SocialStore(root / 'social')
            row = store.create('project-1', local_payload())
            store.queue(row.id)
            graph = FakeMetaTransport()
            binary = FakeBinaryTransport()
            client = MetaGraphClient('user-credential', 'v25.0', transport=graph, binary_transport=binary)
            published = Wave27MetaSocialPublisher(
                store,
                client,
                instagram_media_resolver=lambda _row: media,
                sleep=lambda _seconds: None,
                reel_poll_interval=0,
                reel_poll_attempts=3,
            ).publish(row.id)

            self.assertEqual(published.status, 'PUBLISHED')
            self.assertEqual(published.remote_id, 'ig-media-local')
            start = next(call for call in graph.calls if call[1].endswith('/ig-1/media') and call[2].get('upload_type') == 'resumable')
            self.assertEqual(start[0], 'POST')
            self.assertEqual(start[2]['media_type'], 'REELS')
            self.assertNotIn('video_url', start[2])
            self.assertEqual(start[2]['access_token'], 'user-credential')
            self.assertEqual(len(binary.calls), 1)
            self.assertEqual(binary.calls[0][0], 'https://rupload.facebook.com/ig-api-upload/v25.0/container-local')
            self.assertEqual(binary.calls[0][1], media)
            self.assertEqual(binary.calls[0][2], 'user-credential')
            publish = next(call for call in graph.calls if call[1].endswith('/ig-1/media_publish'))
            self.assertEqual(publish[2]['access_token'], 'user-credential')
            self.assertGreaterEqual(graph.local_status_calls, 2)

    def test_existing_instagram_url_flow_still_uses_linked_page_credential(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Wave27SocialStore(Path(tmp) / 'social')
            row = store.create('project-1', local_payload(render_id=None, media_url='https://cdn.example/reel.mp4'))
            store.queue(row.id)
            graph = FakeMetaTransport()
            client = MetaGraphClient('user-credential', 'v25.0', transport=graph, binary_transport=FakeBinaryTransport())
            published = Wave27MetaSocialPublisher(store, client, sleep=lambda _seconds: None, reel_poll_interval=0).publish(row.id)
            self.assertEqual(published.status, 'PUBLISHED')
            self.assertEqual(published.remote_id, 'ig-media-url')
            create = next(call for call in graph.calls if call[1].endswith('/ig-1/media') and call[2].get('video_url'))
            self.assertEqual(create[2]['access_token'], 'page-credential')
            self.assertNotIn('upload_type', create[2])

    def test_provider_upload_host_is_fail_closed_before_binary_transfer(self):
        graph = FakeMetaTransport(upload_host='example.com')
        binary = FakeBinaryTransport()
        client = MetaGraphClient('user-credential', 'v25.0', transport=graph, binary_transport=binary)
        with self.assertRaisesRegex(MetaGraphError, 'invalid Instagram resumable upload URI'):
            InstagramLocalReelUploader(client).create_container('ig-1', 'caption')
        self.assertEqual(binary.calls, [])

    def test_managed_instagram_render_validates_project_sha_and_provider_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = Path(tmp) / 'data'
            state = data / 'State'
            social_root = state / 'social'
            renders_root = state / 'renders'
            projects_root = data / 'Projects'
            exports = projects_root / 'project-dir' / 'exports'
            social_root.mkdir(parents=True)
            renders_root.mkdir(parents=True)
            exports.mkdir(parents=True)
            media = exports / 'clip.mp4'
            media.write_bytes(b'certified-local-instagram')
            digest = hashlib.sha256(media.read_bytes()).hexdigest()
            (projects_root / 'projects.json').write_text(json.dumps([{'id': 'project-1', 'directory': 'project-dir'}]), encoding='utf-8')
            render = {'id': 'render-1', 'project_id': 'project-1', 'status': 'PASS', 'width': 1080, 'height': 1920, 'start': 0, 'end': 30, 'output_name': 'clip.mp4', 'bytes': media.stat().st_size, 'sha256': digest}
            (renders_root / 'jobs.json').write_text(json.dumps([render]), encoding='utf-8')
            store = Wave27SocialStore(social_root)
            row = store.create('project-1', local_payload())
            self.assertEqual(instagram_managed_render_path(store, row), media.resolve())

            render['sha256'] = '0' * 64
            (renders_root / 'jobs.json').write_text(json.dumps([render]), encoding='utf-8')
            with self.assertRaisesRegex(Exception, 'SHA-256'):
                instagram_managed_render_path(store, row)

            render['sha256'] = digest
            render['end'] = 61
            (renders_root / 'jobs.json').write_text(json.dumps([render]), encoding='utf-8')
            with self.assertRaisesRegex(Exception, 'between 3 and 60'):
                instagram_managed_render_path(store, row)


if __name__ == '__main__':
    unittest.main()
