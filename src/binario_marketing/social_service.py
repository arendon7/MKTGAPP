from __future__ import annotations

import time
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable

from .meta_graph import MetaGraphClient, MetaGraphError
from .social_store import Publication, SocialStore


class SocialPublishError(RuntimeError):
    pass


class MetaSocialPublisher:
    """Executes queued publications using the real Meta Graph API client.

    The scheduler is deliberately deterministic and can be called from a UI/API tick or a future
    launchd worker. It never owns credentials; the Meta client resolves them from process memory.
    """

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
