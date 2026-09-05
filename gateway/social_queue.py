from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol
from urllib.parse import urlparse

from .core import Conflict, GatewayError, TENANT_ID_RE, canonical_json_bytes


REMOTE_SOCIAL_JOB_SCHEMA = "binario.marketing.remote-social-job.v1"
REMOTE_SOCIAL_RECEIPT_SCHEMA = "binario.marketing.remote-social-receipt.v1"
REMOTE_SOCIAL_LEASE_SCHEMA = "binario.marketing.remote-social-lease.v1"
PUBLICATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
PROJECT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
WORKER_ID_RE = re.compile(r"^worker_[0-9a-f]{16}$")
TARGET_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
STATUSES = {"PENDING", "LEASED", "PUBLISHED", "FAILED", "CANCELLED"}
MAX_BODY_BYTES = 64 * 1024
MAX_BATCH = 20
MAX_ATTEMPTS = 5
MIN_LEASE_SECONDS = 30
MAX_LEASE_SECONDS = 15 * 60
MAX_SCHEDULE_DAYS = 366
_SECRET_KEYS = {
    "access_token", "token", "api_key", "apikey", "password", "secret",
    "client_secret", "app_secret", "authorization", "bearer", "service_role",
    "service_role_key", "cookie", "session",
}


class SocialQueueError(GatewayError):
    pass


def _now_iso(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).isoformat()


def _parse_time(value: object, field: str) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise SocialQueueError(f"{field} must be ISO-8601") from None
    if parsed.tzinfo is None:
        raise SocialQueueError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _assert_secret_free(value: object) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).strip().casefold().replace("-", "_")
            if normalized in _SECRET_KEYS:
                raise SocialQueueError("secret-bearing fields are forbidden in remote social jobs")
            _assert_secret_free(child)
    elif isinstance(value, list):
        for child in value:
            _assert_secret_free(child)


def _https_url(value: object, field: str, *, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise SocialQueueError(f"{field} is required")
        return None
    if len(text) > 4096:
        raise SocialQueueError(f"{field} is too long")
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise SocialQueueError(f"{field} must be a credential-free HTTPS URL")
    return text


def _clean_text(value: object, limit: int, field: str, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise SocialQueueError(f"{field} is required")
    if len(text) > limit:
        raise SocialQueueError(f"{field} is too long")
    return text


def validate_remote_social_job(raw_body: bytes, *, now: datetime | None = None) -> dict:
    if len(raw_body) > MAX_BODY_BYTES:
        raise SocialQueueError("remote social job exceeds 64 KiB")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise SocialQueueError("invalid remote social JSON") from None
    if not isinstance(payload, dict) or payload.get("schema") != REMOTE_SOCIAL_JOB_SCHEMA:
        raise SocialQueueError("remote social job schema mismatch")
    if set(payload) != {"schema", "publication", "approval"}:
        raise SocialQueueError("remote social job has unsupported envelope fields")
    _assert_secret_free(payload)

    approval = payload.get("approval")
    if not isinstance(approval, dict) or set(approval) != {"source_status", "operator_approved"}:
        raise SocialQueueError("remote social approval contract is invalid")
    if approval.get("source_status") != "QUEUED" or approval.get("operator_approved") is not True:
        raise SocialQueueError("only explicitly approved QUEUED publications may enter cloud execution")

    publication = payload.get("publication")
    allowed = {
        "id", "project_id", "channel", "target_id", "target_name", "kind", "message",
        "link_url", "media_url", "scheduled_for",
    }
    if not isinstance(publication, dict) or set(publication) - allowed:
        raise SocialQueueError("remote social publication fields are invalid")
    publication_id = str(publication.get("id") or "").strip().lower()
    project_id = str(publication.get("project_id") or "").strip()
    channel = str(publication.get("channel") or "").strip().lower()
    target_id = str(publication.get("target_id") or "").strip()
    target_name = _clean_text(publication.get("target_name"), 160, "target_name")
    kind = str(publication.get("kind") or "").strip().lower()
    message = _clean_text(publication.get("message"), 20000, "message")
    if not PUBLICATION_ID_RE.fullmatch(publication_id):
        raise SocialQueueError("publication id must be the canonical 32-hex local id")
    if not PROJECT_ID_RE.fullmatch(project_id):
        raise SocialQueueError("project_id is invalid")
    if channel not in {"facebook_page", "instagram"}:
        raise SocialQueueError("unsupported remote social channel")
    if not TARGET_ID_RE.fullmatch(target_id):
        raise SocialQueueError("target_id is invalid")

    link_url = _https_url(publication.get("link_url"), "link_url")
    media_url = _https_url(publication.get("media_url"), "media_url")
    if channel == "facebook_page":
        if kind not in {"text", "link", "image"}:
            raise SocialQueueError("cloud Facebook v1 supports text, link and public image only")
        if kind in {"text", "link"} and not message:
            raise SocialQueueError("Facebook text/link requires a message")
        if kind == "link" and not link_url:
            raise SocialQueueError("Facebook link requires link_url")
        if kind == "image" and not media_url:
            raise SocialQueueError("Facebook cloud image requires public media_url")
    else:
        if kind not in {"image", "reel"}:
            raise SocialQueueError("cloud Instagram v1 supports public image and reel only")
        if not media_url:
            raise SocialQueueError("Instagram cloud media requires public media_url")

    scheduled = _parse_time(publication.get("scheduled_for"), "scheduled_for")
    clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if scheduled > clock + timedelta(days=MAX_SCHEDULE_DAYS):
        raise SocialQueueError("scheduled_for is too far in the future")

    normalized = {
        "schema": REMOTE_SOCIAL_JOB_SCHEMA,
        "publication": {
            "id": publication_id,
            "project_id": project_id,
            "channel": channel,
            "target_id": target_id,
            "target_name": target_name,
            "kind": kind,
            "message": message,
            "link_url": link_url,
            "media_url": media_url,
            "scheduled_for": _now_iso(scheduled),
        },
        "approval": {"source_status": "QUEUED", "operator_approved": True},
    }
    _assert_secret_free(normalized)
    return normalized


@dataclass(frozen=True)
class RemoteSocialJob:
    tenant_id: str
    publication_id: str
    payload: dict
    payload_sha256: str
    scheduled_for: str
    available_at: str
    status: str
    attempts: int
    created_at: str
    updated_at: str
    lease_worker_id: str | None = None
    lease_sha256: str | None = None
    lease_expires_at: str | None = None
    remote_id: str | None = None
    last_error: str | None = None


class SocialQueueStorage(Protocol):
    def get(self, tenant_id: str, publication_id: str) -> RemoteSocialJob | None: ...
    def insert(self, row: RemoteSocialJob) -> None: ...
    def list_due(self, tenant_id: str, now_iso: str, limit: int) -> list[RemoteSocialJob]: ...
    def replace(self, row: RemoteSocialJob) -> None: ...
    def requeue_expired(self, tenant_id: str, now_iso: str) -> int: ...


class MemorySocialQueueStorage:
    def __init__(self):
        self.rows: dict[tuple[str, str], RemoteSocialJob] = {}

    def get(self, tenant_id: str, publication_id: str) -> RemoteSocialJob | None:
        return self.rows.get((tenant_id, publication_id))

    def insert(self, row: RemoteSocialJob) -> None:
        key = (row.tenant_id, row.publication_id)
        if key in self.rows:
            raise Conflict("remote social publication already exists")
        self.rows[key] = row

    def list_due(self, tenant_id: str, now_iso: str, limit: int) -> list[RemoteSocialJob]:
        rows = [
            row for row in self.rows.values()
            if row.tenant_id == tenant_id and row.status == "PENDING" and row.available_at <= now_iso
        ]
        return sorted(rows, key=lambda row: (row.available_at, row.scheduled_for, row.publication_id))[:limit]

    def replace(self, row: RemoteSocialJob) -> None:
        key = (row.tenant_id, row.publication_id)
        if key not in self.rows:
            raise KeyError(row.publication_id)
        self.rows[key] = row

    def requeue_expired(self, tenant_id: str, now_iso: str) -> int:
        changed = 0
        for key, row in list(self.rows.items()):
            if row.tenant_id != tenant_id or row.status != "LEASED" or not row.lease_expires_at:
                continue
            if row.lease_expires_at > now_iso:
                continue
            terminal = row.attempts >= MAX_ATTEMPTS
            self.rows[key] = replace(
                row,
                status="FAILED" if terminal else "PENDING",
                available_at=now_iso,
                updated_at=now_iso,
                lease_worker_id=None,
                lease_sha256=None,
                lease_expires_at=None,
                last_error="worker lease expired before completion",
            )
            changed += 1
        return changed


def _tenant(value: str) -> str:
    text = str(value or "").strip().lower()
    if not TENANT_ID_RE.fullmatch(text):
        raise SocialQueueError("invalid tenant id")
    return text


def _publication_id(value: str) -> str:
    text = str(value or "").strip().lower()
    if not PUBLICATION_ID_RE.fullmatch(text):
        raise SocialQueueError("invalid publication id")
    return text


def _lease_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RemoteSocialQueueService:
    """Secret-free remote scheduling state machine. It performs zero provider calls."""

    def __init__(self, storage: SocialQueueStorage):
        self.storage = storage

    def enqueue(self, tenant_id: str, raw_body: bytes, *, now: datetime | None = None) -> tuple[int, dict]:
        tenant = _tenant(tenant_id)
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        payload = validate_remote_social_job(raw_body, now=clock)
        publication = payload["publication"]
        publication_id = publication["id"]
        digest = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
        existing = self.storage.get(tenant, publication_id)
        if existing is not None:
            if hmac.compare_digest(existing.payload_sha256, digest):
                return 200, {
                    "schema": REMOTE_SOCIAL_RECEIPT_SCHEMA,
                    "publication_id": publication_id,
                    "accepted": True,
                    "idempotent_reuse": True,
                    "status": existing.status,
                }
            raise Conflict("publication id already exists with a different remote payload")
        scheduled = publication["scheduled_for"]
        now_iso = _now_iso(clock)
        row = RemoteSocialJob(
            tenant_id=tenant,
            publication_id=publication_id,
            payload=payload,
            payload_sha256=digest,
            scheduled_for=scheduled,
            available_at=scheduled,
            status="PENDING",
            attempts=0,
            created_at=now_iso,
            updated_at=now_iso,
        )
        self.storage.insert(row)
        return 202, {
            "schema": REMOTE_SOCIAL_RECEIPT_SCHEMA,
            "publication_id": publication_id,
            "accepted": True,
            "idempotent_reuse": False,
            "status": "PENDING",
        }

    def claim_due(
        self,
        tenant_id: str,
        worker_id: str,
        *,
        now: datetime | None = None,
        limit: int = 10,
        lease_seconds: int = 120,
    ) -> list[dict]:
        tenant = _tenant(tenant_id)
        worker = str(worker_id or "").strip().lower()
        if not WORKER_ID_RE.fullmatch(worker):
            raise SocialQueueError("invalid worker id")
        if limit < 1 or limit > MAX_BATCH:
            raise SocialQueueError("claim limit must be between 1 and 20")
        if lease_seconds < MIN_LEASE_SECONDS or lease_seconds > MAX_LEASE_SECONDS:
            raise SocialQueueError("lease_seconds must be between 30 and 900")
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        now_iso = _now_iso(clock)
        self.storage.requeue_expired(tenant, now_iso)
        leases: list[dict] = []
        for row in self.storage.list_due(tenant, now_iso, limit):
            current = self.storage.get(tenant, row.publication_id)
            if current is None or current.status != "PENDING" or current.available_at > now_iso:
                continue
            token = secrets.token_hex(32)
            expires = _now_iso(clock + timedelta(seconds=lease_seconds))
            leased = replace(
                current,
                status="LEASED",
                attempts=current.attempts + 1,
                updated_at=now_iso,
                lease_worker_id=worker,
                lease_sha256=_lease_hash(token),
                lease_expires_at=expires,
                last_error=None,
            )
            self.storage.replace(leased)
            leases.append({
                "schema": REMOTE_SOCIAL_LEASE_SCHEMA,
                "publication_id": leased.publication_id,
                "payload": leased.payload,
                "payload_sha256": leased.payload_sha256,
                "attempt": leased.attempts,
                "lease_token": token,
                "lease_expires_at": expires,
            })
        return leases

    def _leased(self, tenant_id: str, publication_id: str, lease_token: str, *, now: datetime) -> RemoteSocialJob:
        tenant = _tenant(tenant_id)
        publication = _publication_id(publication_id)
        row = self.storage.get(tenant, publication)
        if row is None:
            raise KeyError(publication)
        if row.status != "LEASED" or not row.lease_sha256 or not row.lease_expires_at:
            raise Conflict("publication does not hold an active worker lease")
        supplied = _lease_hash(str(lease_token or ""))
        if not hmac.compare_digest(row.lease_sha256, supplied):
            raise Conflict("worker lease token mismatch")
        if _parse_time(row.lease_expires_at, "lease_expires_at") <= now.astimezone(timezone.utc):
            raise Conflict("worker lease expired")
        return row

    def mark_published(
        self,
        tenant_id: str,
        publication_id: str,
        lease_token: str,
        remote_id: str,
        *,
        now: datetime | None = None,
    ) -> RemoteSocialJob:
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        row = self._leased(tenant_id, publication_id, lease_token, now=clock)
        clean_remote = _clean_text(remote_id, 256, "remote_id", required=True)
        updated = replace(
            row,
            status="PUBLISHED",
            remote_id=clean_remote,
            updated_at=_now_iso(clock),
            lease_worker_id=None,
            lease_sha256=None,
            lease_expires_at=None,
            last_error=None,
        )
        self.storage.replace(updated)
        return updated

    def mark_failed(
        self,
        tenant_id: str,
        publication_id: str,
        lease_token: str,
        error: str,
        *,
        retryable: bool,
        now: datetime | None = None,
    ) -> RemoteSocialJob:
        clock = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        row = self._leased(tenant_id, publication_id, lease_token, now=clock)
        clean_error = _clean_text(error, 2000, "error", required=True)
        retry = bool(retryable) and row.attempts < MAX_ATTEMPTS
        backoff = min(3600, 30 * (2 ** max(0, row.attempts - 1)))
        updated = replace(
            row,
            status="PENDING" if retry else "FAILED",
            available_at=_now_iso(clock + timedelta(seconds=backoff)) if retry else row.available_at,
            updated_at=_now_iso(clock),
            lease_worker_id=None,
            lease_sha256=None,
            lease_expires_at=None,
            last_error=clean_error,
        )
        self.storage.replace(updated)
        return updated


__all__ = [
    "MAX_ATTEMPTS", "MAX_BATCH", "MemorySocialQueueStorage", "PUBLICATION_ID_RE",
    "REMOTE_SOCIAL_JOB_SCHEMA", "REMOTE_SOCIAL_LEASE_SCHEMA", "REMOTE_SOCIAL_RECEIPT_SCHEMA",
    "RemoteSocialJob", "RemoteSocialQueueService", "SocialQueueError", "SocialQueueStorage",
    "validate_remote_social_job",
]
