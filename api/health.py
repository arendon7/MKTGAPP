from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler

from api._shared import write_json
from gateway.core import GatewayService
from gateway.supabase_storage import SupabaseRestStorage


def health_response(*, environ: dict[str, str] | None = None, storage_factory=SupabaseRestStorage) -> tuple[int, dict]:
    env = os.environ if environ is None else environ
    try:
        storage = storage_factory()
        GatewayService(storage, str(env.get("BINARIO_GATEWAY_MASTER_SECRET") or ""))
        storage.healthcheck()
    except Exception:
        return 503, {
            "schema": "binario.marketing.public-gateway-health.v1",
            "status": "unavailable",
            "authentication": "HMAC_SHA256_V1",
            "queue": "SUPABASE_POSTGREST",
            "browser_secret_supported": False,
            "ready_for_intake": False,
        }
    return 200, {
        "schema": "binario.marketing.public-gateway-health.v1",
        "status": "ok",
        "authentication": "HMAC_SHA256_V1",
        "queue": "SUPABASE_POSTGREST",
        "browser_secret_supported": False,
        "ready_for_intake": True,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, payload = health_response()
        write_json(self, status, payload)
