from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler

from gateway.core import GatewayError, GatewayService
from gateway.supabase_storage import SupabaseRestStorage


def service() -> GatewayService:
    master = os.environ.get("BINARIO_GATEWAY_MASTER_SECRET", "")
    return GatewayService(SupabaseRestStorage(), master)


def read_body(handler: BaseHTTPRequestHandler, *, max_bytes: int = 64 * 1024) -> bytes:
    raw = handler.headers.get("Content-Length")
    if raw is None:
        raise GatewayError("Content-Length is required")
    try:
        length = int(raw)
    except ValueError:
        raise GatewayError("invalid Content-Length") from None
    if length < 0 or length > max_bytes:
        error = GatewayError("request body is too large")
        error.status = 413
        raise error
    body = handler.rfile.read(length)
    if len(body) != length:
        raise GatewayError("request body ended before Content-Length")
    return body


def write_json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def handle_error(handler: BaseHTTPRequestHandler, exc: Exception) -> None:
    if isinstance(exc, GatewayError):
        write_json(handler, int(getattr(exc, "status", 400)), {"error": str(exc), "schema": "binario.marketing.public-gateway-error.v1"})
        return
    write_json(handler, 500, {"error": "gateway internal error", "schema": "binario.marketing.public-gateway-error.v1"})
