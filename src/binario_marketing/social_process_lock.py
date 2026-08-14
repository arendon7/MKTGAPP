from __future__ import annotations

import fcntl
import threading
import time
from contextlib import contextmanager
from pathlib import Path


_LOCAL_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.Lock] = {}


def _thread_lock(path: Path) -> threading.Lock:
    key = str(Path(path).resolve())
    with _LOCAL_GUARD:
        lock = _LOCAL_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCAL_LOCKS[key] = lock
        return lock


@contextmanager
def social_queue_lock(root: Path, *, timeout: float = 0.0):
    """Own the durable social queue across threads and macOS helper processes."""
    if timeout < 0 or timeout > 30:
        raise ValueError("social queue lock timeout must be between 0 and 30 seconds")
    directory = Path(root)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".queue.lock"
    local = _thread_lock(path)
    deadline = time.monotonic() + timeout
    acquired_local = local.acquire(blocking=False)
    while not acquired_local and timeout > 0 and time.monotonic() < deadline:
        time.sleep(0.05)
        acquired_local = local.acquire(blocking=False)
    if not acquired_local:
        yield False
        return

    handle = None
    acquired_file = False
    try:
        handle = path.open("a+")
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired_file = True
                break
            except BlockingIOError:
                if timeout <= 0 or time.monotonic() >= deadline:
                    break
                time.sleep(0.05)
        yield acquired_file
    finally:
        if handle is not None:
            if acquired_file:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        local.release()


__all__ = ["social_queue_lock"]
