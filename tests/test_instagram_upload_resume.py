import tempfile
import unittest
from pathlib import Path

from binario_marketing.instagram_upload_checkpoint import InstagramUploadCheckpointStore
from binario_marketing.meta_graph import MetaGraphClient
from binario_marketing.wave27_instagram_local import Wave27MetaSocialPublisher, Wave27SocialStore


class ResumeTransport:
    def __init__(self):
        self.calls = []
        self.finished = False

    def __call__(self, method, url, params):
        self.calls.append((method, url, dict(params)))
        path = url.split('/v25.0/', 1)[-1]
        if path == 'ig-1/media':
            return {'id': 'container-1', 'uri': 'https://rupload.facebook.com/ig-api-upload/v25.0/container-1'}
        if path == 'container-1':
            return {'id': 'container-1', 'status_code': 'FINISHED' if self.finished else 'IN_PROGRESS'}
        if path == 'ig-1/media_publish':
            return {'id': 'remote-reel-1'}
        raise AssertionError(path)


class BinaryRecorder:
    def __init__(self):
        self.calls = []

    def __call__(self, upload_url, file_path, credential):
        self.calls.append((upload_url, Path(file_path), credential))
        return {'success': True}


def create_local(store):
    return store.create('project-1', {
        'channel': 'instagram',
        'target_id': 'ig-1',
        'target_name': '@brand',
        'kind': 'reel',
        'message': 'Resume test',
        'render_id': 'render-1',
    })


def queued(store, row):
    current = store.get(row.id)
    if current.status in {'DRAFT', 'FAILED'}:
        return store.queue(row.id)
    return current


class InstagramUploadResumeTests(unittest.TestCase):
    def make_client(self, transport, binary):
        return MetaGraphClient('test-user', 'v25.0', transport=transport, binary_transport=binary)

    def test_retry_after_uploaded_checkpoint_reuses_container_and_skips_second_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / 'clip.mp4'; media.write_bytes(b'instagram-local')
            store = Wave27SocialStore(root / 'social')
            row = create_local(store); queued(store, row)
            transport = ResumeTransport(); binary = BinaryRecorder()
            first = Wave27MetaSocialPublisher(
                store,
                self.make_client(transport, binary),
                instagram_media_resolver=lambda _row: media,
                sleep=lambda _seconds: None,
                reel_poll_interval=0,
                reel_poll_attempts=1,
            ).publish(row.id)
            self.assertEqual(first.status, 'FAILED')
            checkpoint = InstagramUploadCheckpointStore(store.root / 'instagram_uploads').get(row.id)
            self.assertEqual(checkpoint.stage, 'UPLOADED')
            create_calls = len([call for call in transport.calls if call[1].endswith('/ig-1/media')])
            self.assertEqual(create_calls, 1)
            self.assertEqual(len(binary.calls), 1)

            transport.finished = True
            queued(store, row)
            second = Wave27MetaSocialPublisher(
                store,
                self.make_client(transport, binary),
                instagram_media_resolver=lambda _row: (_ for _ in ()).throw(AssertionError('local file must not be resolved again')),
                sleep=lambda _seconds: None,
                reel_poll_interval=0,
                reel_poll_attempts=1,
            ).publish(row.id)
            self.assertEqual(second.status, 'PUBLISHED')
            self.assertEqual(second.remote_id, 'remote-reel-1')
            self.assertEqual(len([call for call in transport.calls if call[1].endswith('/ig-1/media')]), 1)
            self.assertEqual(len(binary.calls), 1)
            checkpoint = InstagramUploadCheckpointStore(store.root / 'instagram_uploads').get(row.id)
            self.assertEqual(checkpoint.stage, 'PUBLISHED')
            self.assertEqual(checkpoint.remote_id, 'remote-reel-1')

    def test_finished_checkpoint_publishes_same_container_without_create_or_upload(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = Wave27SocialStore(root / 'social'); row = create_local(store); queued(store, row)
            checkpoints = InstagramUploadCheckpointStore(store.root / 'instagram_uploads')
            checkpoints.uploaded(row.id, row.project_id, row.target_id, 'container-1'); checkpoints.finished(row.id)
            transport = ResumeTransport(); transport.finished = True; binary = BinaryRecorder()
            result = Wave27MetaSocialPublisher(store, self.make_client(transport, binary), reel_poll_attempts=1).publish(row.id)
            self.assertEqual(result.status, 'PUBLISHED')
            self.assertFalse(any(call[1].endswith('/ig-1/media') for call in transport.calls))
            self.assertEqual(binary.calls, [])
            self.assertTrue(any(call[1].endswith('/ig-1/media_publish') for call in transport.calls))

    def test_publishing_checkpoint_fails_closed_without_provider_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = Wave27SocialStore(root / 'social'); row = create_local(store); queued(store, row)
            checkpoints = InstagramUploadCheckpointStore(store.root / 'instagram_uploads')
            checkpoints.uploaded(row.id, row.project_id, row.target_id, 'container-1'); checkpoints.finished(row.id); checkpoints.publishing(row.id)
            transport = ResumeTransport(); binary = BinaryRecorder()
            result = Wave27MetaSocialPublisher(store, self.make_client(transport, binary), reel_poll_attempts=1).publish(row.id)
            self.assertEqual(result.status, 'FAILED')
            self.assertIn('result is uncertain', result.error)
            self.assertEqual(transport.calls, [])
            self.assertEqual(binary.calls, [])
            self.assertEqual(checkpoints.get(row.id).stage, 'PUBLISHING')

    def test_published_checkpoint_completes_local_publication_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = Wave27SocialStore(root / 'social'); row = create_local(store); queued(store, row)
            checkpoints = InstagramUploadCheckpointStore(store.root / 'instagram_uploads')
            checkpoints.uploaded(row.id, row.project_id, row.target_id, 'container-1'); checkpoints.finished(row.id); checkpoints.publishing(row.id); checkpoints.published(row.id, 'remote-existing')
            transport = ResumeTransport(); binary = BinaryRecorder()
            result = Wave27MetaSocialPublisher(store, self.make_client(transport, binary), reel_poll_attempts=1).publish(row.id)
            self.assertEqual(result.status, 'PUBLISHED')
            self.assertEqual(result.remote_id, 'remote-existing')
            self.assertEqual(transport.calls, [])
            self.assertEqual(binary.calls, [])

    def test_checkpoint_identity_mismatch_is_fail_closed_and_sidecar_is_secret_free(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); store = Wave27SocialStore(root / 'social'); row = create_local(store); queued(store, row)
            checkpoints = InstagramUploadCheckpointStore(store.root / 'instagram_uploads')
            checkpoints.uploaded(row.id, 'other-project', row.target_id, 'container-1')
            transport = ResumeTransport(); binary = BinaryRecorder()
            result = Wave27MetaSocialPublisher(store, self.make_client(transport, binary), reel_poll_attempts=1).publish(row.id)
            self.assertEqual(result.status, 'FAILED')
            self.assertIn('does not match', result.error)
            self.assertEqual(transport.calls, [])
            text = (store.root / 'instagram_uploads' / f'{row.id}.json').read_text(encoding='utf-8').lower()
            for forbidden in ('token', 'credential', 'authorization', 'upload_uri', 'rupload.facebook.com'):
                self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
