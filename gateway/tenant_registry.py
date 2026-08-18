from __future__ import annotations

import hashlib
import hmac
import re
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from .core import Unauthorized


TENANT_ID_RE = re.compile(r"^tenant_[0-9a-f]{24}$")
NONCE_RE = re.compile(r"^[0-9a-f]{32}$")
ACTIVE = "ACTIVE"
REVOKED = "REVOKED"
MAX_VERSION = 2_147_483_647


def _tenant(value: object) -> str:
    text = str(value or "").strip().lower()
    if not TENANT_ID_RE.fullmatch(text):
        raise ValueError("invalid tenant id")
    return text


def _nonce(value: object) -> str:
    text = str(value or "").strip().lower()
    if not NONCE_RE.fullmatch(text):
        raise ValueError("invalid admin request nonce")
    return text


def _version(value: object) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError("invalid credential version") from None
    if number < 1 or number > MAX_VERSION:
        raise ValueError("credential version is outside supported range")
    return number


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass(frozen=True)
class TenantCredentialRecord:
    tenant_id: str
    status: str
    ingress_version: int
    pull_version: int
    created_at: str
    updated_at: str
    revoked_at: str | None = None

    def __post_init__(self) -> None:
        _tenant(self.tenant_id)
        if self.status not in {ACTIVE, REVOKED}:
            raise ValueError("invalid tenant credential status")
        _version(self.ingress_version)
        _version(self.pull_version)
        if self.status == ACTIVE and self.revoked_at is not None:
            raise ValueError("active tenant cannot have revoked_at")
        if self.status == REVOKED and not self.revoked_at:
            raise ValueError("revoked tenant requires revoked_at")


class TenantCredentialRegistry(Protocol):
    def get(self, tenant_id: str) -> TenantCredentialRecord | None: ...
    def register(self, tenant_id: str) -> TenantCredentialRecord: ...
    def rotate(self, tenant_id: str, purpose: str, *, request_nonce: str) -> TenantCredentialRecord: ...
    def revoke(self, tenant_id: str) -> TenantCredentialRecord: ...
    def reactivate(self, tenant_id: str) -> TenantCredentialRecord: ...


class MemoryTenantCredentialRegistry:
    """Deterministic test registry. Production uses SupabaseTenantCredentialRegistry."""

    def __init__(self):
        self.rows: dict[str, TenantCredentialRecord] = {}
        self.audit: list[dict] = []
        self.rotate_nonces: dict[tuple[str, str], str] = {}

    def get(self, tenant_id: str) -> TenantCredentialRecord | None:
        return self.rows.get(_tenant(tenant_id))

    def register(self, tenant_id: str) -> TenantCredentialRecord:
        tenant = _tenant(tenant_id)
        current = self.rows.get(tenant)
        if current:
            return current
        now = _now_iso()
        row = TenantCredentialRecord(tenant, ACTIVE, 1, 1, now, now, None)
        self.rows[tenant] = row
        self.audit.append({"tenant_id": tenant, "action": "REGISTER", "purpose": None, "from_version": None, "to_version": None, "request_nonce": None})
        return row

    def rotate(self, tenant_id: str, purpose: str, *, request_nonce: str) -> TenantCredentialRecord:
        tenant = _tenant(tenant_id)
        nonce = _nonce(request_nonce)
        if purpose not in {"ingress", "pull"}:
            raise ValueError("credential rotation purpose must be ingress or pull")
        replay_key = (tenant, nonce)
        replay_purpose = self.rotate_nonces.get(replay_key)
        if replay_purpose is not None:
            if replay_purpose != purpose:
                raise ValueError("admin nonce was already used for another rotation purpose")
            current = self.rows.get(tenant)
            if not current:
                raise KeyError("tenant is not registered")
            return current
        current = self.rows.get(tenant)
        if not current:
            raise KeyError("tenant is not registered")
        if current.status != ACTIVE:
            raise Unauthorized("tenant is revoked")
        old_version = current.ingress_version if purpose == "ingress" else current.pull_version
        if old_version >= MAX_VERSION:
            raise ValueError("credential version exhausted")
        now = _now_iso()
        row = replace(
            current,
            ingress_version=old_version + 1 if purpose == "ingress" else current.ingress_version,
            pull_version=old_version + 1 if purpose == "pull" else current.pull_version,
            updated_at=now,
        )
        self.rows[tenant] = row
        self.rotate_nonces[replay_key] = purpose
        self.audit.append({
            "tenant_id": tenant,
            "action": "ROTATE_INGRESS" if purpose == "ingress" else "ROTATE_PULL",
            "purpose": purpose,
            "from_version": old_version,
            "to_version": old_version + 1,
            "request_nonce": nonce,
        })
        return row

    def revoke(self, tenant_id: str) -> TenantCredentialRecord:
        tenant = _tenant(tenant_id)
        current = self.rows.get(tenant)
        if not current:
            raise KeyError("tenant is not registered")
        if current.status == REVOKED:
            return current
        now = _now_iso()
        row = replace(current, status=REVOKED, updated_at=now, revoked_at=now)
        self.rows[tenant] = row
        self.audit.append({"tenant_id": tenant, "action": "REVOKE", "purpose": None, "from_version": None, "to_version": None, "request_nonce": None})
        return row

    def reactivate(self, tenant_id: str) -> TenantCredentialRecord:
        tenant = _tenant(tenant_id)
        current = self.rows.get(tenant)
        if not current:
            raise KeyError("tenant is not registered")
        if current.status == ACTIVE:
            return current
        if current.ingress_version >= MAX_VERSION or current.pull_version >= MAX_VERSION:
            raise ValueError("credential version exhausted")
        now = _now_iso()
        row = replace(
            current,
            status=ACTIVE,
            ingress_version=current.ingress_version + 1,
            pull_version=current.pull_version + 1,
            updated_at=now,
            revoked_at=None,
        )
        self.rows[tenant] = row
        self.audit.append({"tenant_id": tenant, "action": "REACTIVATE", "purpose": None, "from_version": None, "to_version": None, "request_nonce": None})
        return row


def derive_admin_secret(master_secret: str) -> str:
    clean = str(master_secret or "").strip()
    if len(clean) < 32 or len(clean) > 4096:
        raise ValueError("gateway master secret must contain 32-4096 characters")
    return hmac.new(clean.encode("utf-8"), b"binario-gateway-v2:tenant-admin", hashlib.sha256).hexdigest()


__all__ = [
    "ACTIVE", "MAX_VERSION", "MemoryTenantCredentialRegistry", "NONCE_RE", "REVOKED", "TenantCredentialRecord",
    "TenantCredentialRegistry", "_nonce", "derive_admin_secret",
]
