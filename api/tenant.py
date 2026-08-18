from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api._shared import handle_error, read_body, tenant_admin_service, write_json


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = read_body(self, max_bytes=8 * 1024)
            status, payload = tenant_admin_service().execute(self.headers, body)
            write_json(self, status, payload)
        except Exception as exc:
            handle_error(self, exc)
