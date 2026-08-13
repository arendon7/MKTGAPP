from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .atomic import write_json_atomic
from .meta_graph import MetaGraphClient
from .meta_instagram_local import InstagramLocalReelUploader, _MAX_INSTAGRAM_REEL_BYTES
from .social_service import MetaSocialPublisher, SocialPublishError, SocialScheduler, _sha256_file
from .social_store import PROJECT_ID_RE, Publication, SocialStore, _assert_secret_free, _now, _parse_when


InstagramMediaResolver = Callable[[Publication], Path]


class Wave27SocialStore(SocialStore):
    """Adds local-render Instagram Reel intent without changing the certified base store."""

    def create(self, project_id: str, payload: dict) -> Publication:
        if not isinstance(payload, dict):
            raise ValueError("publication payload must be an object")
        channel = str(payload.get("channel") or "").strip().lower()
        kind = str(payload.get("kind") or "text").strip().lower()
        if channel != "instagram" or kind != "reel":
            return super().create(project_id, payload)

        _assert_secret_free(payload)
        media_url = str(payload.get("media_url") or "").strip() or None
        render_id = str(payload.get("render_id") or "").strip() or None
        if bool(media_url) == bool(render_id):
            raise ValueError("Instagram Reel requires exactly one of public media_url or completed local render_id")
        if media_url:
            return super().create(project_id, payload)

        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("invalid project id")
        target_id = str(payload.get("target_id") or "").strip()
        if not target_id or len(target_id) > 128:
            raise ValueError("target_id is required")
        message = str(payload.get("message") or "").strip()
        if len(message) > 20000:
            raise ValueError("publication message is too long")
        scheduled = _parse_when(payload.get("scheduled_for"))
        now = _now()
        row = Publication(
            id=uuid.uuid4().hex,
            project_id=project_id,
            channel="instagram",
            target_id=target_id,
            target_name=str(payload.get("target_name") or "").strip()[:160],
            kind="reel",
            message=message,
            link_url=str(payload.get("link_url") or "").strip() or None,
            media_url=None,
            asset_id=str(payload.get("asset_id") or "").strip() or None,
            scheduled_for=scheduled.isoformat() if scheduled else None,
            status="QUEUED" if scheduled is not None else "DRAFT",
            remote_id=None,
            error=None,
            attempts=0,
            created_at=now,
            updated_at=now,
            render_id=render_id,
        )
        with self._lock:
            write_json_atomic(self._path(row.id), asdict(row))
        return row


def instagram_managed_render_path(store: SocialStore, row: Publication) -> Path:
    if row.channel != "instagram" or row.kind != "reel" or not row.render_id:
        raise SocialPublishError("Instagram local Reel requires a completed local render")
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
    render = next((
        item for item in jobs
        if isinstance(item, dict)
        and str(item.get("id")) == row.render_id
        and str(item.get("project_id")) == row.project_id
    ), None)
    if render is None:
        raise SocialPublishError("selected render does not belong to this project")
    if str(render.get("status")) != "PASS":
        raise SocialPublishError("Instagram local Reel requires a completed PASS render")
    try:
        width = int(render.get("width"))
        height = int(render.get("height"))
        duration = float(render.get("end")) - float(render.get("start"))
    except (TypeError, ValueError) as exc:
        raise SocialPublishError("selected render has invalid media metadata") from exc
    if width <= 0 or height <= 0 or width * 16 != height * 9:
        raise SocialPublishError("Instagram local Reel render must be 9:16")
    if width > 1920:
        raise SocialPublishError("Instagram local Reel render exceeds 1920 horizontal pixels")
    if duration < 3 or duration > 60:
        raise SocialPublishError("Instagram local Reel duration must be between 3 and 60 seconds in this certified flow")

    output_name = str(render.get("output_name") or "").strip()
    if not output_name or Path(output_name).name != output_name:
        raise SocialPublishError("selected render output name is invalid")
    if Path(output_name).suffix.lower() not in {".mp4", ".mov"}:
        raise SocialPublishError("Instagram local Reel must use an MP4 or MOV render")

    projects_root = (data_root / "Projects").resolve()
    project_registry = projects_root / "projects.json"
    if not project_registry.is_file():
        raise SocialPublishError("project registry is unavailable")
    try:
        projects = json.loads(project_registry.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise SocialPublishError("project registry is unreadable") from exc
    project = next((item for item in projects if isinstance(item, dict) and str(item.get("id")) == row.project_id), None)
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
    if candidate.stat().st_size > _MAX_INSTAGRAM_REEL_BYTES:
        raise SocialPublishError("Instagram local Reel exceeds the 1 GB provider limit")
    expected_sha = str(render.get("sha256") or "").strip().lower()
    if expected_sha and _sha256_file(candidate).lower() != expected_sha:
        raise SocialPublishError("completed render SHA-256 no longer matches its certified record")
    return candidate


class Wave27MetaSocialPublisher(MetaSocialPublisher):
    def __init__(self, *args, instagram_media_resolver: InstagramMediaResolver | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.instagram_media_resolver = instagram_media_resolver or (lambda row: instagram_managed_render_path(self.store, row))

    def _instagram(self, row: Publication) -> str:
        if row.kind != "reel" or not row.render_id:
            return super()._instagram(row)
        if row.media_url:
            raise SocialPublishError("Instagram local Reel cannot also include a public media URL")
        path = self.instagram_media_resolver(row)
        uploader = InstagramLocalReelUploader(self.client)
        container_id, upload_uri = uploader.create_container(row.target_id, row.message)
        uploader.upload(upload_uri, path)
        final = ""
        for attempt in range(self.reel_poll_attempts):
            status = uploader.status(container_id)
            error = uploader.status_error(status)
            if error:
                raise SocialPublishError(f"Instagram local Reel processing failed: {error}")
            final = uploader.status_code(status)
            if final == "FINISHED":
                return uploader.publish(row.target_id, container_id)
            if attempt + 1 < self.reel_poll_attempts:
                self.sleep(self.reel_poll_interval)
        raise SocialPublishError(f"Instagram local Reel processing timed out with status {final or 'UNKNOWN'}")


class Wave27SocialScheduler(SocialScheduler):
    def run_once(self, now: datetime | None = None, limit: int = 20) -> list[dict]:
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        connection = MetaGraphClient.diagnose_env()
        if not connection.configured:
            self.last_error = None
            return []
        try:
            results = Wave27MetaSocialPublisher(
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


def install_wave27_social(runtime) -> None:
    previous = runtime.social_scheduler
    if previous is not None:
        previous.shutdown()
    runtime.social = Wave27SocialStore(runtime.data_root / "State" / "social")
    runtime.social_scheduler = Wave27SocialScheduler(runtime.social, on_results=runtime._record_social_results)
    runtime.social_scheduler.start()


__all__ = [
    "Wave27MetaSocialPublisher",
    "Wave27SocialScheduler",
    "Wave27SocialStore",
    "install_wave27_social",
    "instagram_managed_render_path",
]
