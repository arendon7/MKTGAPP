from __future__ import annotations

import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable

from .meta_graph import MetaGraphClient, MetaGraphError
from .social_store import Publication, SocialStore


class SocialPublishError(RuntimeError):
    pass


class MetaSocialPublisher:
    """Executes queued publications using the real Meta Graph API client."""

    def __init__(
        self,
        store: SocialStore,
        client: MetaGraphClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        reel_poll_interval: float = 2.0,
        reel_poll_attempts: int = 30,
    ):
        if reel_poll_interval < 0:
            raise ValueError("reel_poll_interval must be non-negative")
        if reel_poll_attempts < 1 or reel_poll_attempts > 300:
            raise ValueError("reel_poll_attempts must be between 1 and 300")
        self.store = store
        self.client = client
        self.sleep = sleep
        self.reel_poll_interval = reel_poll_interval
        self.reel_poll_attempts = reel_poll_attempts

    def _instagram(self, row: Publication) -> str:
        if row.kind not in {"image", "reel"}:
            raise SocialPublishError("Instagram automation currently supports image and reel publications")
        if not row.media_url:
            raise SocialPublishError("Instagram needs a public media URL reachable by Meta")
        container_id = self.client.create_instagram_container(row.target_id, row.media_url, row.message, row.kind)
        if row.kind == "reel":
            final = ""
            for attempt in range(self.reel_poll_attempts):
                final = self.client.instagram_container_status(container_id, row.target_id)
                if final in {"FINISHED", "PUBLISHED"}:
                    break
                if final in {"ERROR", "EXPIRED"}:
                    raise SocialPublishError(f"Instagram reel processing failed with status {final}")
                if attempt + 1 < self.reel_poll_attempts:
                    self.sleep(self.reel_poll_interval)
            else:
                raise SocialPublishError(f"Instagram reel processing timed out with status {final or 'UNKNOWN'}")
        return self.client.publish_instagram_container(row.target_id, container_id)

    def _facebook(self, row: Publication) -> str:
        if row.kind in {"text", "link"}:
            return self.client.publish_page_feed(row.target_id, row.message, row.link_url)
        if row.kind == "image":
            if not row.media_url:
                raise SocialPublishError("Facebook image automation currently requires a public media URL")
            return self.client.publish_page_photo(row.target_id, row.media_url, row.message)
        raise SocialPublishError("Facebook automation currently supports text, link and image publications")

    def publish(self, publication_id: str) -> Publication:
        row = self.store.get(publication_id)
        if row.status != "QUEUED":
            raise ValueError("publication must be QUEUED before publishing")
        row = self.store.transition(publication_id, "PUBLISHING")
        try:
            if row.channel == "facebook_page":
                remote_id = self._facebook(row)
            elif row.channel == "instagram":
                remote_id = self._instagram(row)
            else:
                raise SocialPublishError(f"unsupported social channel: {row.channel}")
            return self.store.transition(publication_id, "PUBLISHED", remote_id=remote_id)
        except (MetaGraphError, SocialPublishError, ValueError) as exc:
            return self.store.transition(publication_id, "FAILED", error=str(exc))
        except Exception as exc:
            return self.store.transition(publication_id, "FAILED", error=f"{type(exc).__name__}: publication failed")

    def run_due(self, now: datetime | None = None, limit: int = 20) -> list[dict]:
        moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        results = []
        for row in self.store.due(moment, limit=limit):
            results.append(asdict(self.publish(row.id)))
        return results


class SocialScheduler:
    """Runs the durable social queue while the desktop service is alive."""

    def __init__(
        self,
        store: SocialStore,
        *,
        client_factory: Callable[[], MetaGraphClient] = MetaGraphClient.from_env,
        interval_seconds: float = 30.0,
        on_results: Callable[[list[dict]], None] | None = None,
    ):
        if interval_seconds < 1 or interval_seconds > 3600:
            raise ValueError("social scheduler interval must be between 1 and 3600 seconds")
        self.store = store
        self.client_factory = client_factory
        self.interval_seconds = interval_seconds
        self.on_results = on_results
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self.last_run_at: str | None = None
        self.last_error: str | None = None
        self.recovered_on_start = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            recovered = self.store.recover_interrupted()
            self.recovered_on_start = len(recovered)
            self._stop.clear()
            if not MetaGraphClient.diagnose_env().configured:
                return
            self._thread = threading.Thread(target=self._loop, name="binario-social-scheduler", daemon=True)
            self._thread.start()

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self.interval_seconds):
                break

    def run_once(self, now: datetime | None = None, limit: int = 20) -> list[dict]:
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        connection = MetaGraphClient.diagnose_env()
        if not connection.configured:
            self.last_error = None
            return []
        try:
            results = MetaSocialPublisher(self.store, self.client_factory()).run_due(now=now, limit=limit)
            self.last_error = None
            if results and self.on_results is not None:
                self.on_results(results)
            return results
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []

    def status(self) -> dict:
        thread = self._thread
        return {
            "running": bool(thread and thread.is_alive() and not self._stop.is_set()),
            "interval_seconds": self.interval_seconds,
            "last_run_at": self.last_run_at,
            "last_error": self.last_error,
            "recovered_on_start": self.recovered_on_start,
        }

    def shutdown(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=min(5.0, self.interval_seconds + 0.5))
