import multiprocessing
import tempfile
import unittest
from pathlib import Path

from binario_marketing.social_process_lock import social_queue_lock


def _hold_lock(root, ready, release):
    with social_queue_lock(Path(root), timeout=2.0) as acquired:
        ready.put(acquired)
        release.wait(5)


class SocialProcessLockTests(unittest.TestCase):
    def test_same_process_contention_is_nonblocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with social_queue_lock(root) as first:
                self.assertTrue(first)
                with social_queue_lock(root) as second:
                    self.assertFalse(second)
            with social_queue_lock(root) as after:
                self.assertTrue(after)

    def test_other_process_cannot_take_lock_until_owner_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            ctx = multiprocessing.get_context('spawn')
            ready = ctx.Queue()
            release = ctx.Event()
            process = ctx.Process(target=_hold_lock, args=(tmp, ready, release))
            process.start()
            try:
                self.assertTrue(ready.get(timeout=10))
                with social_queue_lock(Path(tmp), timeout=0.2) as acquired:
                    self.assertFalse(acquired)
            finally:
                release.set()
                process.join(timeout=10)
                if process.is_alive():
                    process.terminate(); process.join(timeout=5)
            self.assertEqual(process.exitcode, 0)
            with social_queue_lock(Path(tmp), timeout=1.0) as acquired:
                self.assertTrue(acquired)


if __name__ == '__main__':
    unittest.main()
