from __future__ import annotations

import errno
import os
from pathlib import Path

try:  # POSIX: macOS/Linux production and CI.
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - exercised on Windows only.
    fcntl = None

try:  # Windows fallback for source/dev compatibility.
    import msvcrt  # type: ignore
except ImportError:  # pragma: no cover - exercised on POSIX only.
    msvcrt = None


class SocialProcessLock:
    """Non-blocking OS lock for the shared durable social publication queue.

    The lock file contains no credentials or publication data. The kernel-held
    lock, not file existence, is authoritative, so process crashes release it.
    """

    def __init__(self, social_root: Path):
        self.root = Path(social_root)
        self.path = self.root / ".publish-due.lock"
        self._handle = None
        self.acquired = False

    def acquire(self) -> bool:
        if self.acquired:
            return True
        self.root.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
            if fcntl is not None:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    return False
            elif msvcrt is not None:  # pragma: no cover - Windows only.
                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                try:
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as exc:
                    if exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK, 13, 36}:
                        handle.close()
                        return False
                    raise
            else:  # Fail closed rather than claim multi-process safety.
                handle.close()
                raise RuntimeError("inter-process file locking is unavailable on this platform")
        except Exception:
            if not handle.closed:
                handle.close()
            raise
        self._handle = handle
        self.acquired = True
        return True

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            self.acquired = False
            return
        try:
            if self.acquired:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:  # pragma: no cover - Windows only.
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            handle.close()
            self._handle = None
            self.acquired = False

    def __enter__(self) -> "SocialProcessLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
