from __future__ import annotations

import threading
from datetime import datetime

from .meta_graph import MetaGraphClient
from .social_process_lock import social_queue_lock
from .wave27_instagram_local import Wave27SocialScheduler


class LockedSocialScheduler(Wave27SocialScheduler):
    """Wave 27 publishing semantics with one cross-process queue owner at a time."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._recovery_done = False
        self.lock_skips = 0

    def start(self) -> None:
        # Base start() recovers PUBLISHING rows before starting its thread. That is
        # unsafe once the desktop app and LaunchAgent can coexist, so recovery is
        # delayed until this process actually owns the queue lock.
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            if not MetaGraphClient.diagnose_env().configured:
                return
            self._thread = threading.Thread(target=self._loop, name="binario-social-scheduler", daemon=True)
            self._thread.start()

    def run_once(self, now: datetime | None = None, limit: int = 20) -> list[dict]:
        with social_queue_lock(self.store.root, timeout=0.0) as acquired:
            if not acquired:
                self.lock_skips += 1
                return []
            if not self._recovery_done:
                recovered = self.store.recover_interrupted()
                self.recovered_on_start += len(recovered)
                self._recovery_done = True
            return super().run_once(now=now, limit=limit)

    def status(self) -> dict:
        payload = super().status()
        payload["process_lock"] = True
        payload["lock_skips"] = self.lock_skips
        return payload


def install_locked_scheduler(runtime) -> None:
    previous = runtime.social_scheduler
    if previous is not None:
        previous.shutdown()
    runtime.social_scheduler = LockedSocialScheduler(runtime.social, on_results=runtime._record_social_results)
    runtime.social_scheduler.start()


__all__ = ["LockedSocialScheduler", "install_locked_scheduler"]
