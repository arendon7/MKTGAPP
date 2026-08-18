from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api._shared import write_json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        write_json(self, 200, {
            "schema": "binario.marketing.public-gateway-health.v1",
            "status": "ok",
            "authentication": "HMAC_SHA256_V1",
            "queue": "SUPABASE_POSTGREST",
            "browser_secret_supported": False,
        })
