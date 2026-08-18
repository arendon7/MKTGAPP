from __future__ import annotations

import hashlib
import hmac
import json
import re
import time

from .core import (
    ACK_SCHEMA,
    ENVELOPE_SCHEMA,
    MAX_BATCH,
    MAX_CLOCK_SKEW_SECONDS,
    PULL_SCHEMA,
    RETENTION_SECONDS,
    Conflict,
    GatewayError,
    GatewayService,
    StoredEvent,
    Unauthorized,
    _event,
    _headers,
    _iso,
    _tenant,
    canonical_json_bytes,
    envelope_signature,
    request_signature,
    validate_public_lead,
)
from .tenant_registry import ACTIVE, TenantCredentialRegistry


CREDENTIAL_VERSION_HEADER = "X-Binario-Credential-Version"


def derive_versioned_tenant_secret(master_secret: str, tenant_id: str, *, purpose: str, version: int) -> str:
    clean = str(master_secret or "").strip()
    if len(clean) < 32 or len(clean) > 4096:
        raise RuntimeError("BINARIO_GATEWAY_MASTER_SECRET must contain 32-4096 characters")
    tenant = _tenant(tenant_id)
    if purpose not in {"ingress", "pull"}:
        raise ValueError("invalid gateway secret purpose")
    try:
        number = int(version)
    except (TypeError, ValueError):
        raise ValueError("invalid credential version") from None
    if number < 1 or number > 2_147_483_647:
        raise ValueError("credential version is outside supported range")
    if number == 1:
        message = f"binario-gateway-v1:{purpose}:{tenant}"
    else:
        message = f"binario-gateway-v1:{purpose}:{tenant}:v{number}"
    return hmac.new(clean.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


class VersionedGatewayService(GatewayService):
    """Wave 58 gateway: W56 protocol + registry-backed tenant revocation/version enforcement."""

    def __init__(self, storage, master_secret: str, tenant_registry: TenantCredentialRegistry):
        super().__init__(storage, master_secret)
        self.tenant_registry = tenant_registry

    def _authenticate(
        self,
        headers: object,
        *,
        purpose: str,
        method: str,
        path: str,
        body: bytes,
        now: int,
        event_nonce: bool,
    ) -> tuple[str, str, int, str]:
        tenant = _tenant(_headers(headers, "X-Binario-Tenant"))
        row = self.tenant_registry.get(tenant)
        if row is None:
            raise Unauthorized("tenant is not registered")
        if row.status != ACTIVE:
            raise Unauthorized("tenant is revoked")
        expected_version = row.ingress_version if purpose == "ingress" else row.pull_version
        raw_version = _headers(headers, CREDENTIAL_VERSION_HEADER)
        try:
            supplied_version = int(raw_version or "1")
        except ValueError:
            raise Unauthorized("invalid credential version") from None
        if supplied_version != expected_version:
            raise Unauthorized("credential version is stale")

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
        if abs(now - sent) > MAX_CLOCK_SKEW_SECONDS:
            raise Unauthorized("request timestamp outside allowed window")

        secret = derive_versioned_tenant_secret(
            self.master_secret,
            tenant,
            purpose=purpose,
            version=expected_version,
        )
        expected = request_signature(secret, timestamp, nonce, method, path, body)
        supplied = _headers(headers, "X-Binario-Signature")
        if not hmac.compare_digest(expected, supplied):
            raise Unauthorized("invalid request signature")
        return tenant, nonce, expected_version, secret

    def ingest(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant, event_id, version, _ = self._authenticate(
            headers,
            purpose="ingress",
            method="POST",
            path="/api/intake",
            body=raw_body,
            now=clock,
            event_nonce=True,
        )
        payload = validate_public_lead(raw_body)
        canonical = canonical_json_bytes(payload)
        digest = hashlib.sha256(canonical).hexdigest()
        existing = self.storage.get_event(tenant, event_id)
        if existing:
            if hmac.compare_digest(existing.payload_sha256, digest):
                return 200, {
                    "schema": "binario.marketing.public-intake-receipt.v1",
                    "event_id": event_id,
                    "accepted": True,
                    "idempotent_reuse": True,
                    "credential_version": version,
                }
            raise Conflict("event id already exists with a different payload")
        received_at = _iso(clock)
        expires_at = _iso(clock + RETENTION_SECONDS)
        self.storage.insert_event(StoredEvent(tenant, event_id, received_at, expires_at, payload, digest, "PENDING"))
        return 202, {
            "schema": "binario.marketing.public-intake-receipt.v1",
            "event_id": event_id,
            "accepted": True,
            "idempotent_reuse": False,
            "credential_version": version,
        }

    def pull(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant, _, version, secret = self._authenticate(
            headers,
            purpose="pull",
            method="POST",
            path="/api/pull",
            body=raw_body,
            now=clock,
            event_nonce=False,
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
                "credential_version": version,
                "signature": envelope_signature(secret, tenant, row.event_id, row.received_at, row.payload_sha256),
            })
        return 200, {
            "schema": PULL_SCHEMA,
            "tenant_id": tenant,
            "credential_version": version,
            "events": events,
            "count": len(events),
            "background_polling": False,
        }

    def ack(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        tenant, _, version, _ = self._authenticate(
            headers,
            purpose="pull",
            method="POST",
            path="/api/ack",
            body=raw_body,
            now=clock,
            event_nonce=False,
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
        return 200, {
            "schema": ACK_SCHEMA,
            "tenant_id": tenant,
            "credential_version": version,
            "requested": len(clean),
            "acked": acked,
            "payloads_redacted": True,
        }


__all__ = ["CREDENTIAL_VERSION_HEADER", "VersionedGatewayService", "derive_versioned_tenant_secret"]
