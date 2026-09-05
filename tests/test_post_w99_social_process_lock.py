import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.social_process_lock import SocialProcessLock
from binario_marketing.social_service import MetaSocialPublisher, SocialPublishError, SocialScheduler
from binario_marketing.social_store import SocialStore


class FakeFacebookClient:
    def __init__(self):
        self.calls = []

    def publish_page_feed(self, target_id, message, link_url=None):
        self.calls.append((target_id, message, link_url))
        return "page-1_900"


class SocialProcessLockTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "social"
        self.store = SocialStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def _queued(self):
        return self.store.create(
            "project-1",
            {
                "channel": "facebook_page",
                "target_id": "page-1",
                "kind": "text",
                "message": "Publicación protegida",
                "scheduled_for": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            },
        )

    def test_second_process_lock_is_non_blocking_and_first_release_restores_access(self):
        first = SocialProcessLock(self.root)
        second = SocialProcessLock(self.root)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()

    def test_due_runner_skips_without_mutating_when_another_process_owns_queue(self):
        row = self._queued()
        client = FakeFacebookClient()
        publisher = MetaSocialPublisher(self.store, client)
        owner = SocialProcessLock(self.root)
        self.assertTrue(owner.acquire())
        try:
            self.assertEqual(publisher.run_due(), [])
            current = self.store.get(row.id)
            self.assertEqual(current.status, "QUEUED")
            self.assertEqual(current.attempts, 0)
            self.assertEqual(client.calls, [])
        finally:
            owner.release()

        result = publisher.run_due()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["status"], "PUBLISHED")
        self.assertEqual(len(client.calls), 1)

    def test_manual_publish_fails_closed_during_process_contention(self):
        row = self._queued()
        client = FakeFacebookClient()
        publisher = MetaSocialPublisher(self.store, client)
        owner = SocialProcessLock(self.root)
        self.assertTrue(owner.acquire())
        try:
            with self.assertRaisesRegex(SocialPublishError, "busy in another process"):
                publisher.publish(row.id)
            self.assertEqual(self.store.get(row.id).status, "QUEUED")
            self.assertEqual(client.calls, [])
        finally:
            owner.release()

        published = publisher.publish(row.id)
        self.assertEqual(published.status, "PUBLISHED")
        self.assertEqual(len(client.calls), 1)

    def test_scheduler_start_does_not_recover_a_publication_owned_by_another_process(self):
        row = self._queued()
        self.store.transition(row.id, "PUBLISHING")
        owner = SocialProcessLock(self.root)
        self.assertTrue(owner.acquire())
        scheduler = SocialScheduler(self.store, interval_seconds=1)
        try:
            scheduler.start()
            self.assertEqual(self.store.get(row.id).status, "PUBLISHING")
            self.assertEqual(scheduler.recovered_on_start, 0)
        finally:
            scheduler.shutdown()
            owner.release()

        recovered = self.store.recover_interrupted()
        self.assertEqual([item.id for item in recovered], [row.id])
        self.assertEqual(self.store.get(row.id).status, "FAILED")

    def test_lock_file_contains_no_publication_or_credentials(self):
        lock = SocialProcessLock(self.root)
        self.assertTrue(lock.acquire())
        lock.release()
        self.assertTrue(lock.path.is_file())
        self.assertEqual(lock.path.read_bytes().replace(b"\0", b""), b"")


if __name__ == "__main__":
    unittest.main()
