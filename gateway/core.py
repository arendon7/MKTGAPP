from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


PUBLIC_LEAD_SCHEMA = "binario.marketing.public-lead.v1"
ENVELOPE_SCHEMA = "binario.marketing.public-intake-envelope.v1"
PULL_SCHEMA = "binario.marketing.public-intake-pull.v1"
ACK_SCHEMA = "binario.marketing.public-intake-ack.v1"
TENANT_ID_RE = re.compile(r"^tenant_[0-9a-f]{24}$")
EVENT_ID_RE = re.compile(r"^evt_[0-9a-f]{32}$")
MAX_BODY_BYTES = 64 * 1024
MAX_BATCH = 100
MAX_CLOCK_SKEW_SECONDS = 300
RETENTION_SECONDS = 30 * 24 * 3600

LEAD_FIELDS = {
    "name", "organization", "role", "email", "phone", "whatsapp", "instagram",
    "source", "tags", "notes", "attribution_capture",
}
ATTRIBUTION_FIELDS = {
    "bm_tid", "utm_source", "utm_medium", "utm_campaign", "utm_id", "utm_content",
    "utm_term", "utm_source_platform",
}
FORBIDDEN_KEYS = {
    "access_token", "api_key", "apikey", "password", "secret", "client_secret",
    "app_secret", "authorization", "bearer", "service_role", "service_role_key",
}


class GatewayError(RuntimeError):
    status = 400


class Unauthorized(GatewayError):
    status = 401


class Conflict(GatewayError):
    status = 409


class PayloadTooLarge(GatewayError):
    status = 413


def canonical_json_bytes(payload: object) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _tenant(value: object) -> str:
    text = str(value or "").strip().lower()
    if not TENANT_ID_RE.fullmatch(text):
        raise Unauthorized("invalid tenant id")
    return text


def _event(value: object) -> str:
    text = str(value or "").strip().lower()
    if not EVENT_ID_RE.fullmatch(text):
        raise Unauthorized("invalid event id")
    return text


def _master(value: object) -> str:
    clean = str(value or "").strip()
    if len(clean) < 32 or len(clean) > 4096:
        raise RuntimeError("BINARIO_GATEWAY_MASTER_SECRET must contain 32-4096 characters")
    return clean


def derive_tenant_secret(master_secret: str, tenant_id: str, *, purpose: str) -> str:
    if purpose not in {"ingress", "pull"}:
        raise ValueError("invalid gateway secret purpose")
    tenant = _tenant(tenant_id)
    message = f"binario-gateway-v1:{purpose}:{tenant}".encode("utf-8")
    return hmac.new(_master(master_secret).encode("utf-8"), message, hashlib.sha256).hexdigest()


def request_signature(secret_hex: str, timestamp: str, nonce: str, method: str, path: str, body: bytes = b"") -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", str(secret_hex or "")):
        raise Unauthorized("invalid derived secret")
    digest = hashlib.sha256(bytes(body)).hexdigest()
    canonical = f"v1\n{timestamp}\n{nonce}\n{method.upper()}\n{path}\n{digest}".encode("utf-8")
    return "v1=" + hmac.new(bytes.fromhex(secret_hex), canonical, hashlib.sha256).hexdigest()


def envelope_signature(secret_hex: str, tenant_id: str, event_id: str, received_at: str, payload_sha256: str) -> str:
    canonical = f"event-v1\n{_tenant(tenant_id)}\n{_event(event_id)}\n{received_at}\n{payload_sha256}".encode("utf-8")
    return "v1=" + hmac.new(bytes.fromhex(secret_hex), canonical, hashlib.sha256).hexdigest()


def _headers(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    value = getter(name) if getter else None
    return str(value or "").strip()


def _verify_request(master_secret: str, headers: object, *, purpose: str, method: str, path: str, body: bytes, now: int | None = None, event_nonce: bool = False) -> tuple[str, str]:
    tenant = _tenant(_headers(headers, "X-Binario-Tenant"))
    timestamp = _headers(headers, "X-Binario-Timestamp")
    nonce_name = "X-Binario-Event" if event_nonce else "X-Binario-Nonce"
    nonce = _headers(headers, nonce_name).lower()
    if event_nonce:
        _event(nonce)
    elif not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise Unauthorized("invalid request nonce")
    try:
        sent = int(timestamp)
    except ValueError:
        raise Unauthorized("invalid request timestamp") from None
    clock = int(time.time() if now is None else now)
    if abs(clock - sent) > MAX_CLOCK_SKEW_SECONDS:
        raise Unauthorized("request timestamp outside allowed window")
    secret = derive_tenant_secret(master_secret, tenant, purpose=purpose)
    expected = request_signature(secret, timestamp, nonce, method, path, body)
    supplied = _headers(headers, "X-Binario-Signature")
    if not hmac.compare_digest(expected, supplied):
        raise Unauthorized("invalid request signature")
    return tenant, nonce


def _assert_no_secret_keys(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).strip().casefold().replace("-", "_")
            if normalized in FORBIDDEN_KEYS:
                raise GatewayError("secret-bearing fields are forbidden")
            _assert_no_secret_keys(item)
    elif isinstance(value, list):
        for item in value:
            _assert_no_secret_keys(item)


def _text(value: object, limit: int, field: str) -> str | None:
    text = str(value or "").strip()
    if len(text) > limit:
        raise GatewayError(f"{field} is too long")
    return text or None


def validate_public_lead(raw_body: bytes) -> dict:
    if len(raw_body) > MAX_BODY_BYTES:
        raise PayloadTooLarge("public lead payload exceeds 64 KiB")
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise GatewayError("invalid JSON payload") from None
    if not isinstance(payload, dict) or payload.get("schema") != PUBLIC_LEAD_SCHEMA:
        raise GatewayError("public lead schema mismatch")
    if set(payload) - {"schema", "lead", "external_ref"}:
        raise GatewayError("unsupported public lead envelope fields")
    lead = payload.get("lead")
    if not isinstance(lead, dict):
        raise GatewayError("lead must be an object")
    if set(lead) - LEAD_FIELDS:
        raise GatewayError("unsupported lead fields")
    _assert_no_secret_keys(payload)
    for field, limit in {
        "name": 200, "organization": 200, "role": 160, "email": 254,
        "phone": 80, "whatsapp": 80, "instagram": 160, "source": 160, "notes": 4000,
    }.items():
        if field in lead:
            _text(lead.get(field), limit, field)
    tags = lead.get("tags")
    if tags is not None:
        if not isinstance(tags, list) or len(tags) > 30 or any(len(str(tag)) > 40 for tag in tags):
            raise GatewayError("tags must be an array with at most 30 short values")
    capture = lead.get("attribution_capture")
    if capture is not None:
        if not isinstance(capture, dict) or set(capture) - ATTRIBUTION_FIELDS:
            raise GatewayError("invalid attribution_capture fields")
        if any(len(str(value or "")) > 512 for value in capture.values()):
            raise GatewayError("attribution value is too long")
    if "external_ref" in payload:
        _text(payload.get("external_ref"), 256, "external_ref")
    return payload


@dataclass(frozen=True)
class StoredEvent:
    tenant_id: str
    event_id: str
    received_at: str
    expires_at: str
    payload: dict | None
    payload_sha256: str
    status: str


class QueueStorage(Protocol):
    def get_event(self, tenant_id: str, event_id: str) -> StoredEvent | None: ...
    def insert_event(self, event: StoredEvent) -> None: ...
    def list_pending(self, tenant_id: str, limit: int) -> list[StoredEvent]: ...
    def acknowledge(self, tenant_id: str, event_ids: list[str], *, acknowledged_at: str) -> int: ...
    def expire(self, tenant_id: str, *, now_iso: str) -> int: ...


class MemoryQueueStorage:
    def __init__(self):
        self.rows: dict[tuple[str, str], StoredEvent] = {}

    def get_event(self, tenant_id: str, event_id: str) -> StoredEvent | None:
        return self.rows.get((tenant_id, event_id))

    def insert_event(self, event: StoredEvent) -> None:
        key = (event.tenant_id, event.event_id)
        if key in self.rows:
            raise Conflict("event already exists")
        self.rows[key] = event

    def list_pending(self, tenant_id: str, limit: int) -> list[StoredEvent]:
        rows = [row for row in self.rows.values() if row.tenant_id == tenant_id and row.status == "PENDING"]
        return sorted(rows, key=lambda row: (row.received_at, row.event_id))[:limit]

    def acknowledge(self, tenant_id: str, event_ids: list[str], *, acknowledged_at: str) -> int:
        changed = 0
        for event_id in event_ids:
            row = self.rows.get((tenant_id, event_id))
            if row and row.status == "PENDING":
                self.rows[(tenant_id, event_id)] = StoredEvent(row.tenant_id, row.event_id, row.received_at, row.expires_at, None, row.payload_sha256, "ACKED")
                changed += 1
        return changed

    def expire(self, tenant_id: str, *, now_iso: str) -> int:
        changed = 0
        for key, row in list(self.rows.items()):
            if row.tenant_id == tenant_id and row.status == "PENDING" and row.expires_at <= now_iso:
                self.rows[key] = StoredEvent(row.tenant_id, row.event_id, row.received_at, row.expires_at, None, row.payload_sha256, "EXPIRED")
                changed += 1
        return changed


def _iso(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


class GatewayService:
    def __init__(self, storage: QueueStorage, master_secret: str):
        self.storage = storage
        self.master_secret = _master(master_secret)

    def ingest(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant, event_id = _verify_request(
            self.master_secret, headers, purpose="ingress", method="POST", path="/api/intake",
            body=raw_body, now=clock, event_nonce=True,
        )
        payload = validate_public_lead(raw_body)
        canonical = canonical_json_bytes(payload)
        digest = hashlib.sha256(canonical).hexdigest()
        existing = self.storage.get_event(tenant, event_id)
        if existing:
            if hmac.compare_digest(existing.payload_sha256, digest):
                return 200, {"schema": "binario.marketing.public-intake-receipt.v1", "event_id": event_id, "accepted": True, "idempotent_reuse": True}
            raise Conflict("event id already exists with a different payload")
        received_at = _iso(clock)
        expires_at = _iso(clock + RETENTION_SECONDS)
        self.storage.insert_event(StoredEvent(tenant, event_id, received_at, expires_at, payload, digest, "PENDING"))
        return 202, {"schema": "binario.marketing.public-intake-receipt.v1", "event_id": event_id, "accepted": True, "idempotent_reuse": False}

    def pull(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant, _ = _verify_request(
            self.master_secret, headers, purpose="pull", method="POST", path="/api/pull",
            body=raw_body, now=clock, event_nonce=False,
        )
        try:
            payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GatewayError("invalid pull payload") from None
        if not isinstance(payload, dict) or set(payload) - {"limit"}:
            raise GatewayError("invalid pull payload")
        try:
            limit = int(payload.get("limit", 50))
        except (TypeError, ValueError):
            raise GatewayError("invalid pull limit") from None
        limit = max(1, min(limit, MAX_BATCH))
        self.storage.expire(tenant, now_iso=_iso(clock))
        secret = derive_tenant_secret(self.master_secret, tenant, purpose="pull")
        events = []
        for row in self.storage.list_pending(tenant, limit):
            if not isinstance(row.payload, dict):
                continue
            events.append({
                "schema": ENVELOPE_SCHEMA,
                "tenant_id": tenant,
                "event_id": row.event_id,
                "received_at": row.received_at,
                "payload": row.payload,
                "payload_sha256": row.payload_sha256,
                "signature": envelope_signature(secret, tenant, row.event_id, row.received_at, row.payload_sha256),
            })
        return 200, {"schema": PULL_SCHEMA, "tenant_id": tenant, "events": events, "count": len(events), "background_polling": False}

    def ack(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant, _ = _verify_request(
            self.master_secret, headers, purpose="pull", method="POST", path="/api/ack",
            body=raw_body, now=clock, event_nonce=False,
        )
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GatewayError("invalid ack payload") from None
        if not isinstance(payload, dict) or set(payload) != {"event_ids"} or not isinstance(payload["event_ids"], list):
            raise GatewayError("ack payload must contain event_ids")
        clean: list[str] = []
        for value in payload["event_ids"]:
            event_id = _event(value)
            if event_id not in clean:
                clean.append(event_id)
        if not clean or len(clean) > MAX_BATCH:
            raise GatewayError("ack must contain between 1 and 100 event ids")
        acked = self.storage.acknowledge(tenant, clean, acknowledged_at=_iso(clock))
        return 200, {"schema": ACK_SCHEMA, "tenant_id": tenant, "requested": len(clean), "acked": acked, "payloads_redacted": True}


__all__ = [
    "ACK_SCHEMA", "Conflict", "ENVELOPE_SCHEMA", "EVENT_ID_RE", "GatewayError", "GatewayService",
    "MAX_BATCH", "MAX_BODY_BYTES", "MAX_CLOCK_SKEW_SECONDS", "MemoryQueueStorage", "PayloadTooLarge",
    "PUBLIC_LEAD_SCHEMA", "PULL_SCHEMA", "QueueStorage", "RETENTION_SECONDS", "StoredEvent", "TENANT_ID_RE",
    "Unauthorized", "canonical_json_bytes", "derive_tenant_secret", "envelope_signature", "request_signature",
    "validate_public_lead",
]
