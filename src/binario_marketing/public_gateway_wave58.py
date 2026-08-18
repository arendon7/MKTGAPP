from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .atomic import write_json_atomic
from .public_gateway import (
    MAX_GATEWAY_RESPONSE_BYTES,
    PublicGatewayClient,
    _company,
    _gateway_url,
    _master_secret,
    _tenant,
    canonical_json_bytes,
    request_signature,
    verify_envelope,
)
from .social_store import _now


TENANT_STATE_SCHEMA = "binario.marketing.gateway-tenant-state.v1"
ADMIN_SCHEMA = "binario.marketing.gateway-tenant-admin.v1"
ADMIN_PATH = "/api/tenant"


def derive_versioned_tenant_secret(master_secret: str, tenant_id: str, *, purpose: str, version: int) -> str:
    master = _master_secret(master_secret).encode("utf-8")
    tenant = _tenant(tenant_id)
    if purpose not in {"ingress", "pull"}:
        raise ValueError("invalid gateway secret purpose")
    try:
        number = int(version)
    except (TypeError, ValueError):
        raise ValueError("invalid credential version") from None
    if number < 1 or number > 2_147_483_647:
        raise ValueError("credential version is outside supported range")
    message = f"binario-gateway-v1:{purpose}:{tenant}" if number == 1 else f"binario-gateway-v1:{purpose}:{tenant}:v{number}"
    return hmac.new(master, message.encode("utf-8"), hashlib.sha256).hexdigest()


def derive_admin_secret(master_secret: str) -> str:
    master = _master_secret(master_secret).encode("utf-8")
    return hmac.new(master, b"binario-gateway-v2:tenant-admin", hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class GatewayTenantState:
    schema: str
    company_id: str
    tenant_id: str
    status: str
    ingress_version: int
    pull_version: int
    updated_at: str


class GatewayTenantStateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, company_id: str) -> Path:
        return self.root / f"{_company(company_id)}.json"

    def get(self, company_id: str) -> GatewayTenantState | None:
        path = self._path(company_id)
        if not path.exists():
            return None
        row = GatewayTenantState(**json.loads(path.read_text(encoding="utf-8")))
        if row.schema != TENANT_STATE_SCHEMA or row.company_id != _company(company_id):
            raise ValueError("invalid gateway tenant state")
        _tenant(row.tenant_id)
        if row.status not in {"ACTIVE", "REVOKED"}:
            raise ValueError("invalid gateway tenant status")
        if row.ingress_version < 1 or row.pull_version < 1:
            raise ValueError("invalid gateway credential version")
        return row

    def upsert_remote(self, company_id: str, tenant: dict) -> GatewayTenantState:
        company = _company(company_id)
        if not isinstance(tenant, dict):
            raise ValueError("remote tenant state must be an object")
        row = GatewayTenantState(
            schema=TENANT_STATE_SCHEMA,
            company_id=company,
            tenant_id=_tenant(tenant.get("tenant_id")),
            status=str(tenant.get("status") or "").strip().upper(),
            ingress_version=int(tenant.get("ingress_version") or 0),
            pull_version=int(tenant.get("pull_version") or 0),
            updated_at=str(tenant.get("updated_at") or _now()),
        )
        if row.status not in {"ACTIVE", "REVOKED"}:
            raise ValueError("invalid remote gateway tenant status")
        if row.ingress_version < 1 or row.pull_version < 1:
            raise ValueError("invalid remote gateway credential version")
        write_json_atomic(self._path(company), asdict(row))
        return row


class VersionedPublicGatewayClient(PublicGatewayClient):
    def __init__(self, gateway_url: str, tenant_id: str, pull_secret: str, *, pull_version: int, timeout: float = 12.0):
        super().__init__(gateway_url, tenant_id, pull_secret, timeout=timeout)
        self.pull_version = int(pull_version)
        if self.pull_version < 1:
            raise ValueError("invalid pull credential version")

    def _request_json(self, path: str, *, method: str, payload: object | None = None) -> dict:
        body = canonical_json_bytes(payload) if payload is not None else b""
        timestamp = str(int(__import__("time").time()))
        nonce = secrets.token_hex(16)
        signature = request_signature(self.pull_secret, timestamp, nonce, method, path, body)
        request = Request(
            self.gateway_url + path,
            data=body if method == "POST" else None,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Binario-Tenant": self.tenant_id,
                "X-Binario-Timestamp": timestamp,
                "X-Binario-Nonce": nonce,
                "X-Binario-Credential-Version": str(self.pull_version),
                "X-Binario-Signature": signature,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_GATEWAY_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", "replace") if exc.fp else ""
            raise RuntimeError(f"gateway HTTP {exc.code}: {detail[:500]}") from None
        except URLError as exc:
            raise RuntimeError(f"gateway network error: {type(exc.reason).__name__}") from None
        if len(raw) > MAX_GATEWAY_RESPONSE_BYTES:
            raise RuntimeError("gateway response exceeded 5 MiB")
        try:
            decoded = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("gateway returned invalid JSON") from exc
        if not isinstance(decoded, dict):
            raise RuntimeError("gateway response must be an object")
        remote_version = decoded.get("credential_version")
        if remote_version is not None and int(remote_version) != self.pull_version:
            raise RuntimeError("gateway pull credential version mismatch")
        return decoded


def verify_versioned_envelope(envelope: dict, *, tenant_id: str, pull_secret: str, pull_version: int) -> dict:
    if not isinstance(envelope, dict):
        raise ValueError("gateway envelope must be an object")
    version = envelope.get("credential_version")
    if version is None:
        if int(pull_version) != 1:
            raise ValueError("gateway envelope is missing credential version")
    elif int(version) != int(pull_version):
        raise ValueError("gateway envelope credential version mismatch")
    legacy = dict(envelope)
    legacy.pop("credential_version", None)
    return verify_envelope(legacy, tenant_id=tenant_id, pull_secret=pull_secret)


class GatewayTenantAdminClient:
    def __init__(self, gateway_url: str, master_secret: str, *, timeout: float = 12.0):
        self.gateway_url = _gateway_url(gateway_url)
        self.admin_secret = derive_admin_secret(master_secret)
        self.timeout = max(1.0, min(float(timeout), 30.0))

    def execute(self, tenant_id: str, action: str, *, purpose: str | None = None) -> dict:
        tenant = _tenant(tenant_id)
        clean_action = str(action or "").strip().upper()
        payload = {"action": clean_action, "tenant_id": tenant}
        if purpose is not None:
            clean_purpose = str(purpose).strip().lower()
            if clean_purpose not in {"ingress", "pull"}:
                raise ValueError("invalid tenant rotation purpose")
            payload["purpose"] = clean_purpose
        body = canonical_json_bytes(payload)
        timestamp = str(int(__import__("time").time()))
        nonce = secrets.token_hex(16)
        signature = request_signature(self.admin_secret, timestamp, nonce, "POST", ADMIN_PATH, body)
        request = Request(
            self.gateway_url + ADMIN_PATH,
            data=body,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Binario-Admin-Timestamp": timestamp,
                "X-Binario-Admin-Nonce": nonce,
                "X-Binario-Admin-Signature": signature,
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(128 * 1024 + 1)
        except HTTPError as exc:
            detail = exc.read(2048).decode("utf-8", "replace") if exc.fp else ""
            raise RuntimeError(f"gateway tenant admin HTTP {exc.code}: {detail[:500]}") from None
        except URLError as exc:
            raise RuntimeError(f"gateway tenant admin network error: {type(exc.reason).__name__}") from None
        if len(raw) > 128 * 1024:
            raise RuntimeError("gateway tenant admin response exceeded 128 KiB")
        try:
            result = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("gateway tenant admin returned invalid JSON") from exc
        if not isinstance(result, dict) or result.get("schema") != ADMIN_SCHEMA:
            raise RuntimeError("gateway tenant admin schema mismatch")
        if result.get("secret_returned") is not False or result.get("master_secret_returned") is not False:
            raise RuntimeError("gateway tenant admin weakened secret boundary")
        remote = result.get("tenant")
        if not isinstance(remote, dict) or _tenant(remote.get("tenant_id")) != tenant:
            raise RuntimeError("gateway tenant admin tenant mismatch")
        return result


__all__ = [
    "ADMIN_PATH", "ADMIN_SCHEMA", "GatewayTenantAdminClient", "GatewayTenantState", "GatewayTenantStateStore",
    "TENANT_STATE_SCHEMA", "VersionedPublicGatewayClient", "derive_admin_secret", "derive_versioned_tenant_secret",
    "verify_versioned_envelope",
]
