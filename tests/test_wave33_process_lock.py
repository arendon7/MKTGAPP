import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path

from binario_marketing.social_process_lock import social_queue_lock


def _hold_lock(root: str, ready, release):
    with social_queue_lock(Path(root), timeout=2.0) as acquired:
        ready.put(acquired)
        if acquired:
            release.get(timeout=10)


class SocialProcessLockTests(unittest.TestCase):
    def test_same_process_contention_is_nonblocking_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "social"
            with social_queue_lock(root, timeout=0.0) as first:
                self.assertTrue(first)
                with social_queue_lock(root, timeout=0.0) as second:
                    self.assertFalse(second)
            with social_queue_lock(root, timeout=0.0) as after:
                self.assertTrue(after)
            self.assertTrue((root / ".queue.lock").is_file())

    def test_spawned_process_excludes_parent_and_releases_on_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "social"
            ctx = multiprocessing.get_context("spawn")
            ready = ctx.Queue()
            release = ctx.Queue()
            process = ctx.Process(target=_hold_lock, args=(str(root), ready, release))
            process.start()
            self.assertTrue(ready.get(timeout=10))
            with social_queue_lock(root, timeout=0.0) as parent_acquired:
                self.assertFalse(parent_acquired)
            release.put(True)
            process.join(timeout=10)
            self.assertEqual(process.exitcode, 0)
            with social_queue_lock(root, timeout=1.0) as after:
                self.assertTrue(after)

    def test_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "social"
            with social_queue_lock(root, timeout=0.0) as first:
                self.assertTrue(first)
                started = time.monotonic()
                with social_queue_lock(root, timeout=0.12) as second:
                    self.assertFalse(second)
                elapsed = time.monotonic() - started
                self.assertGreaterEqual(elapsed, 0.08)
                self.assertLess(elapsed, 1.0)


if __name__ == "__main__":
    unittest.main()
