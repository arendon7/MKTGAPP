from __future__ import annotations

import uuid
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .company_media_store import CompanyMediaStore, MEDIA_ID_RE
from .meta_graph import MetaGraphClient
from .meta_instagram_local import _MAX_INSTAGRAM_REEL_BYTES
from .social_service import SocialPublishError, _managed_render_path
from .social_store import CHANNELS, PROJECT_ID_RE, Publication, _assert_secret_free, _now, _parse_when
from .video.render import media_duration, probe_media
from .wave27_instagram_local import (
    Wave27MetaSocialPublisher,
    Wave27SocialScheduler,
    Wave27SocialStore,
    instagram_managed_render_path,
)


class Wave34SocialStore(Wave27SocialStore):
    """Adds company-library local Reel intent while preserving every Wave 27 path."""

    def create(self, project_id: str, payload: dict) -> Publication:
        if not isinstance(payload, dict):
            raise ValueError("publication payload must be an object")
        channel = str(payload.get("channel") or "").strip().lower()
        kind = str(payload.get("kind") or "text").strip().lower()
        asset_id = str(payload.get("asset_id") or "").strip() or None
        if kind != "reel" or not asset_id:
            return super().create(project_id, payload)
        if not MEDIA_ID_RE.fullmatch(asset_id):
            return super().create(project_id, payload)

        _assert_secret_free(payload)
        if channel not in CHANNELS:
            raise ValueError("unsupported social channel")
        if channel not in {"facebook_page", "instagram"}:
            raise ValueError("company local Reel supports Facebook or Instagram")
        media_url = str(payload.get("media_url") or "").strip() or None
        render_id = str(payload.get("render_id") or "").strip() or None
        if media_url or render_id:
            raise ValueError("company local Reel uses asset_id only; media_url and render_id must be empty")
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
            channel=channel,
            target_id=target_id,
            target_name=str(payload.get("target_name") or "").strip()[:160],
            kind="reel",
            message=message,
            link_url=None,
            media_url=None,
            asset_id=asset_id,
            scheduled_for=scheduled.isoformat() if scheduled else None,
            status="QUEUED" if scheduled is not None else "DRAFT",
            remote_id=None,
            error=None,
            attempts=0,
            created_at=now,
            updated_at=now,
            render_id=None,
        )
        with self._lock:
            write_json_atomic(self._path(row.id), asdict(row))
        return row


def _probe_company_video(media_store: CompanyMediaStore, company_id: str, media_id: str):
    if not MEDIA_ID_RE.fullmatch(str(media_id or "")):
        raise SocialPublishError("company local Reel requires a managed media asset")
    media = media_store.get_for_company(company_id, media_id)
    if media.kind != "video":
        raise SocialPublishError("local Reel requires a video from the company library")
    path = media_store.verify_file(company_id, media_id)

    width, height, duration = media.width, media.height, media.duration
    if width is None or height is None or duration is None:
        try:
            payload = probe_media(path)
            video_stream = next(
                (stream for stream in payload.get("streams", []) if str(stream.get("codec_type")) == "video"),
                None,
            )
            if not isinstance(video_stream, dict):
                raise SocialPublishError("managed company video has no video stream")
            width = int(video_stream.get("width") or 0)
            height = int(video_stream.get("height") or 0)
            duration = float(media_duration(payload))
            media = media_store.update_probe(
                company_id,
                media_id,
                width=width,
                height=height,
                duration=duration,
            )
        except SocialPublishError:
            raise
        except Exception as exc:
            raise SocialPublishError("managed company video metadata could not be verified") from exc
    return media, path, int(width), int(height), float(duration)


def company_media_reel_path(media_store: CompanyMediaStore, company_id: str, media_id: str, *, provider: str) -> Path:
    media, path, width, height, duration = _probe_company_video(media_store, company_id, media_id)
    suffix = path.suffix.lower()
    if suffix not in {".mp4", ".mov"}:
        raise SocialPublishError("local Reel must use an MP4 or MOV file")
    if width <= 0 or height <= 0 or width * 16 != height * 9:
        raise SocialPublishError("local Reel must be 9:16")

    if provider == "instagram":
        if width > 1920:
            raise SocialPublishError("Instagram local Reel exceeds 1920 horizontal pixels")
        if duration < 3 or duration > 60:
            raise SocialPublishError("Instagram local Reel duration must be between 3 and 60 seconds in this certified flow")
        if media.bytes > _MAX_INSTAGRAM_REEL_BYTES:
            raise SocialPublishError("Instagram local Reel exceeds the 1 GB provider limit")
        return path

    if provider == "facebook":
        if width < 540 or height < 960:
            raise SocialPublishError("Facebook local Reel must be at least 540x960")
        if duration < 4 or duration > 60:
            raise SocialPublishError("Facebook local Reel duration must be between 4 and 60 seconds")
        return path

    raise SocialPublishError("unsupported local Reel provider")


def company_reel_path(media_store: CompanyMediaStore, row: Publication, *, provider: str) -> Path:
    if not row.asset_id:
        raise SocialPublishError("company local Reel requires a managed media asset")
    return company_media_reel_path(media_store, row.project_id, row.asset_id, provider=provider)


class Wave34MetaSocialPublisher(Wave27MetaSocialPublisher):
    """Uses company media for local Reels and delegates project-render behavior unchanged."""

    def __init__(self, store, client, *, media_store: CompanyMediaStore, **kwargs):
        self.company_media = media_store

        def facebook_resolver(row: Publication) -> Path:
            if row.asset_id and MEDIA_ID_RE.fullmatch(row.asset_id):
                return company_reel_path(self.company_media, row, provider="facebook")
            return _managed_render_path(store, row)

        def instagram_resolver(row: Publication) -> Path:
            if row.asset_id and MEDIA_ID_RE.fullmatch(row.asset_id):
                return company_reel_path(self.company_media, row, provider="instagram")
            return instagram_managed_render_path(store, row)

        super().__init__(
            store,
            client,
            local_media_resolver=facebook_resolver,
            instagram_media_resolver=instagram_resolver,
            **kwargs,
        )

    def _instagram(self, row: Publication) -> str:
        if row.kind == "reel" and row.asset_id and MEDIA_ID_RE.fullmatch(row.asset_id) and not row.render_id:
            if row.media_url:
                raise SocialPublishError("company local Instagram Reel cannot also use a public media URL")
            ephemeral = replace(row, render_id=row.asset_id)
            return super()._instagram(ephemeral)
        return super()._instagram(row)


class Wave34SocialScheduler(Wave27SocialScheduler):
    def __init__(self, *args, media_store: CompanyMediaStore, **kwargs):
        super().__init__(*args, **kwargs)
        self.company_media = media_store

    def run_once(self, now: datetime | None = None, limit: int = 20) -> list[dict]:
        self.last_run_at = datetime.now(timezone.utc).isoformat()
        connection = MetaGraphClient.diagnose_env()
        if not connection.configured:
            self.last_error = None
            return []
        try:
            results = Wave34MetaSocialPublisher(
                self.store,
                self.client_factory(),
                media_store=self.company_media,
            ).run_due(now=now, limit=limit)
            self.last_error = None
            if results and self.on_results is not None:
                self.on_results(results)
            return results
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"
            return []


def install_wave34_social(runtime) -> None:
    previous = runtime.social_scheduler
    if previous is not None:
        previous.shutdown()
    runtime.social = Wave34SocialStore(runtime.data_root / "State" / "social")
    runtime.social_scheduler = Wave34SocialScheduler(
        runtime.social,
        media_store=runtime.company_media,
        on_results=runtime._record_social_results,
    )
    runtime.social_scheduler.start()


__all__ = [
    "Wave34MetaSocialPublisher",
    "Wave34SocialScheduler",
    "Wave34SocialStore",
    "company_media_reel_path",
    "company_reel_path",
    "install_wave34_social",
]
