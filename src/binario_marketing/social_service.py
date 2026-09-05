from __future__ import annotations

import hashlib
import json
import threading
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .meta_graph import MetaGraphClient, MetaGraphError
from .social_process_lock import SocialProcessLock
from .social_store import Publication, SocialStore


class SocialPublishError(RuntimeError):
    pass


LocalMediaResolver = Callable[[Publication], Path]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _managed_render_path(store: SocialStore, row: Publication) -> Path:
    if not row.render_id:
        raise SocialPublishError("Facebook Reel requires a completed local render")
    state_root = store.root.parent.resolve()
    data_root = state_root.parent.resolve()
    registry = state_root / "renders" / "jobs.json"
    if not registry.is_file():
        raise SocialPublishError("render registry is unavailable")
    try:
        jobs = json.loads(registry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SocialPublishError("render registry is unreadable") from exc
    if not isinstance(jobs, list):
        raise SocialPublishError("render registry is invalid")
    render = next(
        (
            item for item in jobs
            if isinstance(item, dict)
            and str(item.get("id")) == row.render_id
            and str(item.get("project_id")) == row.project_id
        ),
        None,
    )
    if render is None:
        raise SocialPublishError("selected render does not belong to this project")
    if str(render.get("status")) != "PASS":
        raise SocialPublishError("Facebook Reel requires a completed PASS render")
    try:
        width = int(render.get("width"))
        height = int(render.get("height"))
        duration = float(render.get("end")) - float(render.get("start"))
    except (TypeError, ValueError) as exc:
        raise SocialPublishError("selected render has invalid media metadata") from exc
    if width * 16 != height * 9:
        raise SocialPublishError("Facebook Reel render must be 9:16")
    if width < 540 or height < 960:
        raise SocialPublishError("Facebook Reel render must be at least 540x960")
    if duration < 4 or duration > 60:
        raise SocialPublishError("Facebook Reel render duration must be between 4 and 60 seconds")
    output_name = str(render.get("output_name") or "").strip()
    if not output_name or Path(output_name).name != output_name:
        raise SocialPublishError("selected render output name is invalid")

    projects_root = (data_root / "Projects").resolve()
    project_registry = projects_root / "projects.json"
    if not project_registry.is_file():
        raise SocialPublishError("project registry is unavailable")
    try:
        projects = json.loads(project_registry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SocialPublishError("project registry is unreadable") from exc
    project = next(
        (
            item for item in projects
            if isinstance(item, dict) and str(item.get("id")) == row.project_id
        ),
        None,
    )
    if project is None:
        raise SocialPublishError("publication project is unavailable")
    directory = str(project.get("directory") or "").strip()
    if not directory or Path(directory).name != directory:
        raise SocialPublishError("project directory is invalid")
    exports_root = (projects_root / directory / "exports").resolve()
    if projects_root not in exports_root.parents:
        raise SocialPublishError("project exports path escaped managed root")
    candidate = (exports_root / output_name).resolve()
    if exports_root not in candidate.parents:
        raise SocialPublishError("render output escaped managed exports root")
    if not candidate.is_file():
        raise SocialPublishError("completed render file is missing")
    expected_size = render.get("bytes")
    if expected_size is not None and candidate.stat().st_size != int(expected_size):
        raise SocialPublishError("completed render size no longer matches its certified record")
    expected_sha = str(render.get("sha256") or "").strip().lower()
    if expected_sha and _sha256_file(candidate).lower() != expected_sha:
        raise SocialPublishError("completed render SHA-256 no longer matches its certified record")
    return candidate


class MetaSocialPublisher:
    """Executes queued publications using the real Meta Graph API client."""

    def __init__(
        self,
        store: SocialStore,
        client: MetaGraphClient,
        *,
        local_media_resolver: LocalMediaResolver | None = None,
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
        self.local_media_resolver = local_media_resolver or (lambda row: _managed_render_path(store, row))
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
        if row.kind == "reel":
            path = self.local_media_resolver(row)
            return self.client.publish_page_reel_local(row.target_id, path, row.message)
        raise SocialPublishError("Facebook automation currently supports text, link, image and local Reel publications")

    def _publish_unlocked(self, publication_id: str) -> Publication:
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
        except (MetaGraphError, SocialPublishError, ValueError, FileNotFoundError) as exc:
            return self.store.transition(publication_id, "FAILED", error=str(exc))
        except Exception as exc:
            return self.store.transition(publication_id, "FAILED", error=f"{type(exc).__name__}: publication failed")

    def publish(self, publication_id: str) -> Publication:
        process_lock = SocialProcessLock(self.store.root)
        if not process_lock.acquire():
            raise SocialPublishError("social publication queue is busy in another process")
        try:
            return self._publish_unlocked(publication_id)
        finally:
            process_lock.release()

    def run_due(self, now: datetime | None = None, limit: int = 20) -> list[dict]:
        process_lock = SocialProcessLock(self.store.root)
        if not process_lock.acquire():
            return []
        try:
            moment = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            results = []
            for row in self.store.due(moment, limit=limit):
                results.append(asdict(self._publish_unlocked(row.id)))
            return results
        finally:
            process_lock.release()


class SocialScheduler:
    """Runs the durable social queue while the desktop service is alive."""

    def __init__(
        self,
        store: SocialStore,
        *,
        client_factory: Callable[[], MetaGraphClient] = MetaGraphClient.from_env,
        local_media_resolver: LocalMediaResolver | None = None,
        interval_seconds: float = 30.0,
        on_results: Callable[[list[dict]], None] | None = None,
    ):
        if interval_seconds < 1 or interval_seconds > 3600:
            raise ValueError("social scheduler interval must be between 1 and 3600 seconds")
        self.store = store
        self.client_factory = client_factory
        self.local_media_resolver = local_media_resolver
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
            process_lock = SocialProcessLock(self.store.root)
            if process_lock.acquire():
                try:
                    recovered = self.store.recover_interrupted()
                    self.recovered_on_start = len(recovered)
                finally:
                    process_lock.release()
            else:
                self.recovered_on_start = 0
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
            results = MetaSocialPublisher(
                self.store,
                self.client_factory(),
                local_media_resolver=self.local_media_resolver,
            ).run_due(now=now, limit=limit)
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
