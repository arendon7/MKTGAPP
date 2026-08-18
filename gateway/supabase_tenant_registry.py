from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .tenant_registry import TenantCredentialRecord, _tenant


TABLE = "binario_gateway_tenants"
AUDIT_TABLE = "binario_gateway_tenant_audit"
MAX_RESPONSE_BYTES = 512 * 1024


class SupabaseTenantCredentialRegistry:
    """Service-role-only adapter for Wave 58 tenant control metadata and atomic RPCs."""

    def __init__(self, url: str | None = None, secret_key: str | None = None, *, timeout: float = 10.0):
        self.url = str(url or os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
        self.key = str(secret_key or os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if not self.url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use HTTPS")
        if not self.key:
            raise RuntimeError("SUPABASE_SECRET_KEY is required")
        self.timeout = max(1.0, min(float(timeout), 30.0))

    def _headers(self) -> dict[str, str]:
        headers = {"apikey": self.key, "Accept": "application/json", "Content-Type": "application/json"}
        if self.key.count(".") == 2:
            headers["Authorization"] = f"Bearer {self.key}"
        return headers

    def _request(self, method: str, path: str, payload: object | None = None) -> object:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if payload is not None else None
        request = Request(self.url + path, data=body, method=method, headers=self._headers())
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", "replace") if exc.fp else ""
            raise RuntimeError(f"Supabase tenant registry HTTP {exc.code}: {detail[:700]}") from None
        except URLError as exc:
            raise RuntimeError(f"Supabase tenant registry network error: {type(exc.reason).__name__}") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Supabase tenant registry response exceeded 512 KiB")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Supabase tenant registry returned invalid JSON") from exc

    @staticmethod
    def _record(payload: object) -> TenantCredentialRecord:
        row = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(row, dict):
            raise RuntimeError("Supabase tenant registry row is missing")
        return TenantCredentialRecord(
            tenant_id=str(row.get("tenant_id") or ""),
            status=str(row.get("status") or ""),
            ingress_version=int(row.get("ingress_version") or 0),
            pull_version=int(row.get("pull_version") or 0),
            created_at=str(row.get("created_at") or ""),
            updated_at=str(row.get("updated_at") or ""),
            revoked_at=str(row["revoked_at"]) if row.get("revoked_at") else None,
        )

    def healthcheck(self) -> bool:
        query = "?" + urlencode({"select": "tenant_id", "limit": "1"})
        data = self._request("GET", f"/rest/v1/{TABLE}{query}")
        if not isinstance(data, list):
            raise RuntimeError("Supabase tenant registry health response must be an array")
        return True

    def get(self, tenant_id: str) -> TenantCredentialRecord | None:
        tenant = _tenant(tenant_id)
        query = "?" + urlencode({
            "select": "tenant_id,status,ingress_version,pull_version,created_at,updated_at,revoked_at",
            "tenant_id": f"eq.{tenant}",
            "limit": "1",
        })
        data = self._request("GET", f"/rest/v1/{TABLE}{query}")
        if not isinstance(data, list) or not data:
            return None
        return self._record(data)

    def _rpc(self, name: str, payload: dict) -> TenantCredentialRecord:
        return self._record(self._request("POST", f"/rest/v1/rpc/{name}", payload))

    def register(self, tenant_id: str) -> TenantCredentialRecord:
        return self._rpc("binario_gateway_tenant_register", {"p_tenant_id": _tenant(tenant_id)})

    def rotate(self, tenant_id: str, purpose: str) -> TenantCredentialRecord:
        if purpose not in {"ingress", "pull"}:
            raise ValueError("credential rotation purpose must be ingress or pull")
        return self._rpc("binario_gateway_tenant_rotate", {"p_tenant_id": _tenant(tenant_id), "p_purpose": purpose})

    def revoke(self, tenant_id: str) -> TenantCredentialRecord:
        return self._rpc("binario_gateway_tenant_revoke", {"p_tenant_id": _tenant(tenant_id)})

    def reactivate(self, tenant_id: str) -> TenantCredentialRecord:
        return self._rpc("binario_gateway_tenant_reactivate", {"p_tenant_id": _tenant(tenant_id)})

    def audit(self, tenant_id: str, *, limit: int = 50) -> list[dict]:
        tenant = _tenant(tenant_id)
        bounded = max(1, min(int(limit), 100))
        query = "?" + urlencode({
            "select": "audit_id,tenant_id,action,purpose,from_version,to_version,actor,occurred_at",
            "tenant_id": f"eq.{tenant}",
            "order": "occurred_at.desc,audit_id.desc",
            "limit": str(bounded),
        })
        data = self._request("GET", f"/rest/v1/{AUDIT_TABLE}{query}")
        if not isinstance(data, list):
            raise RuntimeError("Supabase tenant audit response must be an array")
        return [row for row in data if isinstance(row, dict)]


__all__ = ["AUDIT_TABLE", "SupabaseTenantCredentialRegistry", "TABLE"]
