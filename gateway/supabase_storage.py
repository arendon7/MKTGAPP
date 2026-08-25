from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .core import Conflict, StoredEvent


TABLE = "binario_public_intake_queue"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class SupabaseRestStorage:
    """Server-only queue storage using Supabase PostgREST and a backend secret key."""

    def __init__(self, url: str | None = None, secret_key: str | None = None, *, timeout: float = 10.0):
        self.url = str(url or os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
        self.key = str(secret_key or os.environ.get("SUPABASE_SECRET_KEY") or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
        if not self.url.startswith("https://"):
            raise RuntimeError("SUPABASE_URL must use HTTPS")
        if not self.key:
            raise RuntimeError("SUPABASE_SECRET_KEY is required")
        self.timeout = max(1.0, min(float(timeout), 30.0))

    def _headers(self, *, prefer: str | None = None) -> dict[str, str]:
        headers = {"apikey": self.key, "Accept": "application/json", "Content-Type": "application/json"}
        if self.key.count(".") == 2:
            headers["Authorization"] = f"Bearer {self.key}"
        if prefer:
            headers["Prefer"] = prefer
        return headers

    def _request(self, method: str, query: str = "", payload: object | None = None, *, prefer: str | None = None) -> object:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.url}/rest/v1/{TABLE}{query}",
            data=body,
            method=method,
            headers=self._headers(prefer=prefer),
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            detail = exc.read(4096).decode("utf-8", "replace") if exc.fp else ""
            if exc.code == 409:
                raise Conflict("queue row conflict") from None
            raise RuntimeError(f"Supabase queue HTTP {exc.code}: {detail[:700]}") from None
        except URLError as exc:
            raise RuntimeError(f"Supabase queue network error: {type(exc.reason).__name__}") from None
        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Supabase queue response exceeded 2 MiB")
        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError("Supabase queue returned invalid JSON") from exc

    def healthcheck(self) -> bool:
        """Prove that the configured backend credential can read the dedicated queue table."""
        query = "?" + urlencode({"select": "tenant_id", "limit": "1"})
        data = self._request("GET", query)
        if not isinstance(data, list):
            raise RuntimeError("Supabase queue health response must be an array")
        return True

    @staticmethod
    def _row(payload: dict) -> StoredEvent:
        body = payload.get("body_json")
        return StoredEvent(
            tenant_id=str(payload["tenant_id"]),
            event_id=str(payload["event_id"]),
            received_at=str(payload["received_at"]),
            expires_at=str(payload["expires_at"]),
            payload=body if isinstance(body, dict) else None,
            payload_sha256=str(payload["body_sha256"]),
            status=str(payload["status"]),
        )

    def get_event(self, tenant_id: str, event_id: str) -> StoredEvent | None:
        query = "?" + urlencode({
            "select": "tenant_id,event_id,received_at,expires_at,body_json,body_sha256,status",
            "tenant_id": f"eq.{tenant_id}",
            "event_id": f"eq.{event_id}",
            "limit": "1",
        })
        data = self._request("GET", query)
        if not isinstance(data, list) or not data:
            return None
        return self._row(data[0])

    def insert_event(self, event: StoredEvent) -> None:
        payload = {
            "tenant_id": event.tenant_id,
            "event_id": event.event_id,
            "received_at": event.received_at,
            "expires_at": event.expires_at,
            "body_json": event.payload,
            "body_sha256": event.payload_sha256,
            "status": event.status,
        }
        self._request("POST", payload=payload, prefer="return=minimal")

    def list_pending(self, tenant_id: str, limit: int) -> list[StoredEvent]:
        query = "?" + urlencode({
            "select": "tenant_id,event_id,received_at,expires_at,body_json,body_sha256,status",
            "tenant_id": f"eq.{tenant_id}",
            "status": "eq.PENDING",
            "order": "received_at.asc,event_id.asc",
            "limit": str(limit),
        })
        data = self._request("GET", query)
        if not isinstance(data, list):
            raise RuntimeError("Supabase queue list response must be an array")
        return [self._row(row) for row in data if isinstance(row, dict)]

    def acknowledge(self, tenant_id: str, event_ids: list[str], *, acknowledged_at: str) -> int:
        changed = 0
        for event_id in event_ids:
            query = "?" + urlencode({
                "tenant_id": f"eq.{tenant_id}",
                "event_id": f"eq.{event_id}",
                "status": "eq.PENDING",
            })
            data = self._request(
                "PATCH",
                query,
                {"status": "ACKED", "acked_at": acknowledged_at, "body_json": None},
                prefer="return=representation",
            )
            if isinstance(data, list):
                changed += len(data)
        return changed

    def expire(self, tenant_id: str, *, now_iso: str) -> int:
        query = "?" + urlencode({
            "tenant_id": f"eq.{tenant_id}",
            "status": "eq.PENDING",
            "expires_at": f"lt.{now_iso}",
        })
        data = self._request(
            "PATCH",
            query,
            {"status": "EXPIRED", "body_json": None},
            prefer="return=representation",
        )
        return len(data) if isinstance(data, list) else 0


__all__ = ["SupabaseRestStorage", "TABLE"]
