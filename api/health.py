from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler

from api._shared import write_json
from gateway.core import GatewayService
from gateway.supabase_storage import SupabaseRestStorage
from gateway.supabase_tenant_registry import SupabaseTenantCredentialRegistry
from gateway.versioned_service import VersionedGatewayService


def health_response(
    *,
    environ: dict[str, str] | None = None,
    storage_factory=SupabaseRestStorage,
    registry_factory=None,
) -> tuple[int, dict]:
    env = os.environ if environ is None else environ
    registry_required = registry_factory is not None
    try:
        storage = storage_factory()
        master = str(env.get("BINARIO_GATEWAY_MASTER_SECRET") or "")
        if registry_required:
            registry = registry_factory()
            VersionedGatewayService(storage, master, registry)
            registry.healthcheck()
        else:
            GatewayService(storage, master)
        storage.healthcheck()
    except Exception:
        return 503, {
            "schema": "binario.marketing.public-gateway-health.v1",
            "status": "unavailable",
            "authentication": "HMAC_SHA256_V1",
            "queue": "SUPABASE_POSTGREST",
            "tenant_registry": "REQUIRED" if registry_required else "LEGACY_NOT_REQUIRED",
            "browser_secret_supported": False,
            "ready_for_intake": False,
        }
    return 200, {
        "schema": "binario.marketing.public-gateway-health.v1",
        "status": "ok",
        "authentication": "HMAC_SHA256_V1_VERSIONED",
        "queue": "SUPABASE_POSTGREST",
        "tenant_registry": "READY" if registry_required else "LEGACY_NOT_REQUIRED",
        "browser_secret_supported": False,
        "ready_for_intake": True,
    }


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        status, payload = health_response(registry_factory=SupabaseTenantCredentialRegistry)
        write_json(self, status, payload)
