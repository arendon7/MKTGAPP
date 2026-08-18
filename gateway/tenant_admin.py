from __future__ import annotations

import hmac
import json
import re
import time
from dataclasses import asdict

from .core import MAX_CLOCK_SKEW_SECONDS, GatewayError, Unauthorized, request_signature
from .tenant_registry import TenantCredentialRegistry, _tenant, derive_admin_secret


ADMIN_SCHEMA = "binario.marketing.gateway-tenant-admin.v1"
ADMIN_PATH = "/api/tenant"


def _header(headers: object, name: str) -> str:
    getter = getattr(headers, "get", None)
    value = getter(name) if getter else None
    return str(value or "").strip()


class TenantAdminService:
    """Explicit remote tenant control. Authentication uses a master-derived admin key, never a site/pull key."""

    def __init__(self, registry: TenantCredentialRegistry, master_secret: str):
        self.registry = registry
        self.admin_secret = derive_admin_secret(master_secret)

    def _verify(self, headers: object, raw_body: bytes, *, now: int) -> str:
        timestamp = _header(headers, "X-Binario-Admin-Timestamp")
        nonce = _header(headers, "X-Binario-Admin-Nonce").lower()
        if not re.fullmatch(r"[0-9a-f]{32}", nonce):
            raise Unauthorized("invalid admin nonce")
        try:
            sent = int(timestamp)
        except ValueError:
            raise Unauthorized("invalid admin timestamp") from None
        if abs(now - sent) > MAX_CLOCK_SKEW_SECONDS:
            raise Unauthorized("admin timestamp outside allowed window")
        expected = request_signature(self.admin_secret, timestamp, nonce, "POST", ADMIN_PATH, raw_body)
        supplied = _header(headers, "X-Binario-Admin-Signature")
        if not hmac.compare_digest(expected, supplied):
            raise Unauthorized("invalid admin signature")
        return nonce

    @staticmethod
    def _payload(row, *, action: str, idempotent: bool = False) -> dict:
        result = asdict(row)
        return {
            "schema": ADMIN_SCHEMA,
            "action": action,
            "tenant": result,
            "idempotent": bool(idempotent),
            "secret_returned": False,
            "master_secret_returned": False,
        }

    def execute(self, headers: object, raw_body: bytes, *, now: int | None = None) -> tuple[int, dict]:
        clock = int(time.time() if now is None else now)
        request_nonce = self._verify(headers, raw_body, now=clock)
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise GatewayError("invalid tenant admin payload") from None
        if not isinstance(payload, dict):
            raise GatewayError("tenant admin payload must be an object")
        unknown = set(payload) - {"action", "tenant_id", "purpose"}
        if unknown:
            raise GatewayError("unsupported tenant admin fields")
        action = str(payload.get("action") or "").strip().upper()
        tenant = _tenant(payload.get("tenant_id"))
        purpose = str(payload.get("purpose") or "").strip().lower()

        if action == "STATUS":
            if purpose:
                raise GatewayError("STATUS does not accept purpose")
            row = self.registry.get(tenant)
            if row is None:
                error = GatewayError("tenant is not registered")
                error.status = 404
                raise error
            return 200, self._payload(row, action=action, idempotent=True)
        if action == "REGISTER":
            if purpose:
                raise GatewayError("REGISTER does not accept purpose")
            before = self.registry.get(tenant)
            row = self.registry.register(tenant)
            return (200 if before else 201), self._payload(row, action=action, idempotent=before is not None)
        if action == "ROTATE":
            if purpose not in {"ingress", "pull"}:
                raise GatewayError("ROTATE requires ingress or pull purpose")
            before = self.registry.get(tenant)
            row = self.registry.rotate(tenant, purpose, request_nonce=request_nonce)
            old_version = (before.ingress_version if purpose == "ingress" else before.pull_version) if before else None
            new_version = row.ingress_version if purpose == "ingress" else row.pull_version
            replay = old_version is not None and new_version == old_version
            return 200, self._payload(row, action=f"ROTATE_{purpose.upper()}", idempotent=replay)
        if action == "REVOKE":
            if purpose:
                raise GatewayError("REVOKE does not accept purpose")
            before = self.registry.get(tenant)
            row = self.registry.revoke(tenant)
            return 200, self._payload(row, action=action, idempotent=bool(before and before.status == "REVOKED"))
        if action == "REACTIVATE":
            if purpose:
                raise GatewayError("REACTIVATE does not accept purpose")
            before = self.registry.get(tenant)
            row = self.registry.reactivate(tenant)
            return 200, self._payload(row, action=action, idempotent=bool(before and before.status == "ACTIVE"))
        raise GatewayError("unsupported tenant admin action")


__all__ = ["ADMIN_PATH", "ADMIN_SCHEMA", "TenantAdminService"]
