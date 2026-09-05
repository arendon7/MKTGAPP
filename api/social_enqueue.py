from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api._shared import handle_error, read_body, write_json
from api._social_shared import social_service


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = read_body(self, max_bytes=64 * 1024)
            status, payload = social_service().enqueue(self.headers, body)
            write_json(self, status, payload)
        except Exception as exc:
            handle_error(self, exc)

    def do_GET(self):
        write_json(self, 405, {"error": "method not allowed"})
