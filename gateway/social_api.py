from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from typing import Protocol

from .core import GatewayError, MAX_CLOCK_SKEW_SECONDS, TENANT_ID_RE, Unauthorized, request_signature
from .social_queue import PUBLICATION_ID_RE, RemoteSocialQueueService


SOCIAL_ENQUEUE_PATH = "/api/social_enqueue"
SOCIAL_STATUS_PATH = "/api/social_status"
SOCIAL_STATUS_SCHEMA = "binario.marketing.remote-social-status.v1"
SOCIAL_SECRET_PURPOSE = "social"


class SocialReadableStorage(Protocol):
    def get(self, tenant_id: str, publication_id: str): ...
    def insert(self, row): ...


def _master(value: object) -> str:
    clean = str(value or "").strip()
    if len(clean) < 32 or len(clean) > 4096:
        raise RuntimeError("BINARIO_GATEWAY_MASTER_SECRET must contain 32-4096 characters")
    return clean


def _tenant(value: object) -> str:
    text = str(value or "").strip().lower()
    if not TENANT_ID_RE.fullmatch(text):
        raise Unauthorized("invalid tenant id")
    return text


def _headers(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    value = getter(name) if getter else None
    return str(value or "").strip()


def derive_social_secret(master_secret: str, tenant_id: str) -> str:
    tenant = _tenant(tenant_id)
    message = f"binario-gateway-v1:{SOCIAL_SECRET_PURPOSE}:{tenant}".encode("utf-8")
    return hmac.new(_master(master_secret).encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_social_request(
    master_secret: str,
    headers: object,
    *,
    method: str,
    path: str,
    body: bytes,
    now: int | None = None,
) -> str:
    if path not in {SOCIAL_ENQUEUE_PATH, SOCIAL_STATUS_PATH}:
        raise Unauthorized("unsupported social API path")
    tenant = _tenant(_headers(headers, "X-Binario-Tenant"))
    timestamp = _headers(headers, "X-Binario-Timestamp")
    nonce = _headers(headers, "X-Binario-Nonce").lower()
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise Unauthorized("invalid request nonce")
    try:
        sent = int(timestamp)
    except ValueError:
        raise Unauthorized("invalid request timestamp") from None
    clock = int(time.time() if now is None else now)
    if abs(clock - sent) > MAX_CLOCK_SKEW_SECONDS:
        raise Unauthorized("request timestamp outside allowed window")
    expected = request_signature(derive_social_secret(master_secret, tenant), timestamp, nonce, method, path, body)
    supplied = _headers(headers, "X-Binario-Signature")
    if not hmac.compare_digest(expected, supplied):
        raise Unauthorized("invalid request signature")
    return tenant


def social_request_headers(
    social_secret: str,
    tenant_id: str,
    *,
    method: str,
    path: str,
    body: bytes,
    timestamp: int,
    nonce: str,
) -> dict[str, str]:
    """Sign with the tenant's derived social secret; never requires the master secret."""
    tenant = _tenant(tenant_id)
    clean_nonce = str(nonce or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{32}", clean_nonce):
        raise Unauthorized("invalid request nonce")
    if not re.fullmatch(r"[0-9a-f]{64}", str(social_secret or "")):
        raise Unauthorized("invalid social signing secret")
    stamp = str(int(timestamp))
    signature = request_signature(social_secret, stamp, clean_nonce, method, path, body)
    return {
        "X-Binario-Tenant": tenant,
        "X-Binario-Timestamp": stamp,
        "X-Binario-Nonce": clean_nonce,
        "X-Binario-Signature": signature,
    }


def _status_body(raw_body: bytes) -> str:
    if len(raw_body) > 4096:
        raise GatewayError("social status body is too large")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GatewayError("invalid social status JSON") from None
    if not isinstance(payload, dict) or set(payload) != {"publication_id"}:
        raise GatewayError("social status body must contain publication_id only")
    publication_id = str(payload.get("publication_id") or "").strip().lower()
    if not PUBLICATION_ID_RE.fullmatch(publication_id):
        raise GatewayError("invalid publication id")
    return publication_id


class SocialQueueGatewayService:
    """Signed enqueue/status facade with zero social-provider execution authority."""

    def __init__(self, storage: SocialReadableStorage, master_secret: str):
        self.storage = storage
        self.master_secret = _master(master_secret)
        self.queue = RemoteSocialQueueService(storage)

    def enqueue(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant = verify_social_request(
            self.master_secret,
            headers,
            method="POST",
            path=SOCIAL_ENQUEUE_PATH,
            body=raw_body,
            now=clock,
        )
        from datetime import datetime, timezone
        return self.queue.enqueue(tenant, raw_body, now=datetime.fromtimestamp(clock, tz=timezone.utc))

    def status(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant = verify_social_request(
            self.master_secret,
            headers,
            method="POST",
            path=SOCIAL_STATUS_PATH,
            body=raw_body,
            now=clock,
        )
        publication_id = _status_body(raw_body)
        row = self.storage.get(tenant, publication_id)
        if row is None:
            return 404, {
                "schema": SOCIAL_STATUS_SCHEMA,
                "publication_id": publication_id,
                "found": False,
            }
        return 200, {
            "schema": SOCIAL_STATUS_SCHEMA,
            "publication_id": row.publication_id,
            "found": True,
            "status": row.status,
            "attempts": row.attempts,
            "scheduled_for": row.scheduled_for,
            "available_at": row.available_at,
            "remote_id": row.remote_id,
            "updated_at": row.updated_at,
            "provider_error_exposed": False,
            "lease_exposed": False,
        }


__all__ = [
    "SOCIAL_ENQUEUE_PATH", "SOCIAL_SECRET_PURPOSE", "SOCIAL_STATUS_PATH", "SOCIAL_STATUS_SCHEMA",
    "SocialQueueGatewayService", "derive_social_secret", "social_request_headers", "verify_social_request",
]
