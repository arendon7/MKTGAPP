from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .meta_graph import MetaGraphClient, MetaGraphError


_ALLOWED_UPLOAD_HOST = "rupload.facebook.com"
_MAX_INSTAGRAM_REEL_BYTES = 1_000_000_000


def _validated_upload_uri(value: str) -> str:
    uri = str(value or "").strip()
    parsed = urlparse(uri)
    if (
        parsed.scheme != "https"
        or (parsed.hostname or "").lower() != _ALLOWED_UPLOAD_HOST
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in (None, 443)
    ):
        raise MetaGraphError("Meta returned an invalid Instagram resumable upload URI")
    return uri


def _phase_error(payload: dict) -> str | None:
    video_status = payload.get("video_status")
    if not isinstance(video_status, dict):
        return None
    for phase_name in ("uploading_phase", "processing_phase"):
        phase = video_status.get(phase_name)
        if not isinstance(phase, dict) or str(phase.get("status") or "").lower() != "error":
            continue
        errors = phase.get("errors")
        if isinstance(errors, list):
            for row in errors:
                if isinstance(row, dict) and row.get("message"):
                    return str(row["message"])[:500]
        return f"{phase_name} failed"
    return None


class InstagramLocalReelUploader:
    """Current Meta Facebook-Login resumable flow for a managed local Reel."""

    def __init__(self, client: MetaGraphClient):
        self.client = client

    def create_container(self, instagram_id: str, caption: str = "") -> tuple[str, str]:
        account = str(instagram_id or "").strip()
        if not account:
            raise ValueError("Instagram professional account id is required")
        payload = self.client._request(
            "POST",
            f"{account}/media",
            {"media_type": "REELS", "upload_type": "resumable", "caption": str(caption or "")},
        )
        container_id = str(payload.get("id") or "").strip()
        if not container_id:
            raise MetaGraphError("Meta did not return an Instagram resumable container id")
        return container_id, _validated_upload_uri(str(payload.get("uri") or ""))

    def upload(self, upload_uri: str, file_path: Path) -> dict:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(path)
        size = path.stat().st_size
        if size <= 0:
            raise ValueError("Instagram Reel file is empty")
        if size > _MAX_INSTAGRAM_REEL_BYTES:
            raise ValueError("Instagram Reel file exceeds the 1 GB provider limit")
        return self.client._binary_transport(
            _validated_upload_uri(upload_uri),
            path,
            self.client._access_token,
        )

    def status(self, container_id: str) -> dict:
        container = str(container_id or "").strip()
        if not container:
            raise ValueError("Instagram container id is required")
        return self.client._request("GET", container, {"fields": "id,status,status_code,video_status"})

    @staticmethod
    def status_code(payload: dict) -> str:
        return str(payload.get("status_code") or payload.get("status") or "").strip().upper()

    @staticmethod
    def status_error(payload: dict) -> str | None:
        code = InstagramLocalReelUploader.status_code(payload)
        if code in {"ERROR", "EXPIRED"}:
            return str(payload.get("status") or code)[:500]
        return _phase_error(payload)

    def publish(self, instagram_id: str, container_id: str) -> str:
        account = str(instagram_id or "").strip()
        container = str(container_id or "").strip()
        if not account or not container:
            raise ValueError("Instagram account and container ids are required")
        payload = self.client._request("POST", f"{account}/media_publish", {"creation_id": container})
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return an Instagram media id")
        return remote_id


__all__ = ["InstagramLocalReelUploader", "_MAX_INSTAGRAM_REEL_BYTES", "_validated_upload_uri"]
