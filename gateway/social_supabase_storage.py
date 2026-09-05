from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from .core import Conflict
from .social_queue import RemoteSocialJob


TABLE = "binario_social_publish_queue"
CLAIM_RPC = "binario_claim_social_publish_jobs"
BEGIN_EFFECT_RPC = "binario_begin_social_provider_effect"
COMPLETE_RPC = "binario_complete_social_publish_job"
FAIL_RPC = "binario_fail_social_publish_job"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class SupabaseSocialQueueStorage:
    """Server-only PostgREST adapter for the isolated outbound social queue.

    Browser/desktop callers never receive the Supabase service-role credential. All
    distributed worker state changes use dedicated SQL RPCs bound to a one-time lease;
    generic list-then-update mutations remain deliberately unavailable.
    """

    def __init__(self, url: str | None = None, secret_key: str | None = None, *, timeout: float = 10.0):
        self.url = str(url or os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
        parsed = urlparse(self.url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise RuntimeError("SUPABASE_URL must be a credential-free HTTPS origin")
        self.key = str(
            secret_key
            or os.environ.get("SUPABASE_SECRET_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or ""
        ).strip()
        if not self.key:
            raise RuntimeError("SUPABASE_SECRET_KEY is required")
        self.timeout = max(1.0, min(float(timeout), 30.0))

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {
            "apikey": self.key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.key.count(".") == 2:
            headers["Authorization"] = f"Bearer {self.key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(
        self,
        method: str,
        resource: str,
        query: str = "",
        payload: object | None = None,
        *,
        prefer: str | None = None,
    ) -> object:
        body = (
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            if payload is not None else None
        )
        request = Request(
            f"{self.url}/rest/v1/{resource}{query}",
            data=body,
            method=method,
            headers=self._headers(prefer=prefer),
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            # Never echo backend response bodies: worker diagnostics can contain remote
            # provider text and the service-role credential must never be reflected.
            if exc.code == 409:
                raise Conflict("remote social queue row conflict") from None
            raise RuntimeError(f"Supabase social queue HTTP {exc.code}") from None
        except URLError as exc:
            raise RuntimeError(f"Supabase social queue network error: {type(exc.reason).__name__}") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Supabase social queue response exceeded 2 MiB")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Supabase social queue returned invalid JSON") from exc

    @staticmethod
    def _row(payload: dict) -> RemoteSocialJob:
        body = payload.get("body_json")
        if not isinstance(body, dict):
            raise RuntimeError("Supabase social queue row has invalid body_json")
        return RemoteSocialJob(
            tenant_id=str(payload["tenant_id"]),
            publication_id=str(payload["publication_id"]),
            payload=body,
            payload_sha256=str(payload["body_sha256"]),
            scheduled_for=str(payload["scheduled_for"]),
            available_at=str(payload["available_at"]),
            status=str(payload["status"]),
            attempts=int(payload.get("attempts") or 0),
            created_at=str(payload["created_at"]),
            updated_at=str(payload["updated_at"]),
            lease_worker_id=str(payload["lease_worker_id"]) if payload.get("lease_worker_id") else None,
            lease_sha256=str(payload["lease_sha256"]) if payload.get("lease_sha256") else None,
            lease_expires_at=str(payload["lease_expires_at"]) if payload.get("lease_expires_at") else None,
            remote_id=str(payload["remote_id"]) if payload.get("remote_id") else None,
            last_error=str(payload["last_error"]) if payload.get("last_error") else None,
        )

    @staticmethod
    def _select() -> str:
        return (
            "tenant_id,publication_id,body_json,body_sha256,scheduled_for,available_at,status,"
            "attempts,lease_worker_id,lease_sha256,lease_expires_at,remote_id,last_error,created_at,updated_at"
        )

    def get(self, tenant_id: str, publication_id: str) -> RemoteSocialJob | None:
        query = "?" + urlencode({
            "select": self._select(),
            "tenant_id": f"eq.{tenant_id}",
            "publication_id": f"eq.{publication_id}",
            "limit": "1",
        })
        data = self._request("GET", TABLE, query)
        if not isinstance(data, list) or not data:
            return None
        if not isinstance(data[0], dict):
            raise RuntimeError("Supabase social queue get response is invalid")
        return self._row(data[0])

    def insert(self, row: RemoteSocialJob) -> None:
        payload = {
            "tenant_id": row.tenant_id,
            "publication_id": row.publication_id,
            "body_json": row.payload,
            "body_sha256": row.payload_sha256,
            "scheduled_for": row.scheduled_for,
            "available_at": row.available_at,
            "status": row.status,
            "attempts": row.attempts,
            "lease_worker_id": row.lease_worker_id,
            "lease_sha256": row.lease_sha256,
            "lease_expires_at": row.lease_expires_at,
            "remote_id": row.remote_id,
            "last_error": row.last_error,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
        self._request("POST", TABLE, payload=payload, prefer="return=minimal")

    def claim_due_atomic(
        self,
        tenant_id: str,
        worker_id: str,
        *,
        now_iso: str,
        limit: int = 10,
        lease_seconds: int = 120,
    ) -> list[dict]:
        payload = {
            "p_tenant_id": tenant_id,
            "p_worker_id": worker_id,
            "p_now": now_iso,
            "p_limit": int(limit),
            "p_lease_seconds": int(lease_seconds),
        }
        data = self._request("POST", f"rpc/{CLAIM_RPC}", payload=payload)
        if not isinstance(data, list):
            raise RuntimeError("Supabase social claim response must be an array")
        return [row for row in data if isinstance(row, dict)]

    def begin_provider_effect_atomic(
        self,
        tenant_id: str,
        publication_id: str,
        lease_token: str,
        *,
        now_iso: str,
    ) -> None:
        data = self._request(
            "POST",
            f"rpc/{BEGIN_EFFECT_RPC}",
            payload={
                "p_tenant_id": tenant_id,
                "p_publication_id": publication_id,
                "p_lease_token": lease_token,
                "p_now": now_iso,
            },
        )
        if data is not True:
            raise RuntimeError("Supabase did not confirm provider-effect checkpoint")

    def mark_published_atomic(
        self,
        tenant_id: str,
        publication_id: str,
        lease_token: str,
        remote_id: str,
        *,
        now_iso: str,
    ) -> None:
        data = self._request(
            "POST",
            f"rpc/{COMPLETE_RPC}",
            payload={
                "p_tenant_id": tenant_id,
                "p_publication_id": publication_id,
                "p_lease_token": lease_token,
                "p_remote_id": remote_id,
                "p_now": now_iso,
            },
        )
        if data is not True:
            raise RuntimeError("Supabase did not confirm social publication completion")

    def mark_failed_atomic(
        self,
        tenant_id: str,
        publication_id: str,
        lease_token: str,
        error: str,
        *,
        retryable: bool,
        now_iso: str,
    ) -> dict:
        data = self._request(
            "POST",
            f"rpc/{FAIL_RPC}",
            payload={
                "p_tenant_id": tenant_id,
                "p_publication_id": publication_id,
                "p_lease_token": lease_token,
                "p_error": str(error),
                "p_retryable": bool(retryable),
                "p_now": now_iso,
            },
        )
        if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
            raise RuntimeError("Supabase social failure response is invalid")
        return data[0]

    # Deliberately refuse the non-atomic protocol methods. Production distributed
    # workers must use the dedicated lease-bound RPCs above.
    def list_due(self, tenant_id: str, now_iso: str, limit: int) -> list[RemoteSocialJob]:
        raise RuntimeError("distributed social workers must use claim_due_atomic")

    def replace(self, row: RemoteSocialJob) -> None:
        raise RuntimeError("distributed social workers must use lease-bound completion RPCs")

    def requeue_expired(self, tenant_id: str, now_iso: str) -> int:
        raise RuntimeError("expired leases are recovered atomically by claim_due_atomic")


__all__ = [
    "BEGIN_EFFECT_RPC", "CLAIM_RPC", "COMPLETE_RPC", "FAIL_RPC", "MAX_RESPONSE_BYTES",
    "SupabaseSocialQueueStorage", "TABLE",
]
