from __future__ import annotations

from http.server import BaseHTTPRequestHandler

from api._shared import handle_error, read_body, service, write_json


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            body = read_body(self)
            status, payload = service().ingest(self.headers, body)
            write_json(self, status, payload)
        except Exception as exc:
            handle_error(self, exc)

    def do_GET(self):
        write_json(self, 405, {"error": "method not allowed"})
