from __future__ import annotations

import re
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave43_app as base
from .crm_csv import MAX_CSV_BYTES, export_contacts_csv, import_contacts_csv, preview_contacts_csv


class AppRuntime(base.AppRuntime):
    """Wave 44 adds local, company-scoped CRM CSV portability."""

    def preview_crm_contacts_csv(self, company_id: str, csv_text: str) -> dict:
        company = self.companies.get(company_id)
        payload = preview_contacts_csv(self.crm, company.id, csv_text)
        return {"company_id": company.id, **payload}

    def import_crm_contacts_csv(self, company_id: str, csv_text: str) -> dict:
        company = self.companies.get(company_id)
        payload = import_contacts_csv(self.crm, company.id, csv_text)
        self.workspace.registries.timeline.append("crm.contacts.csv.imported", {
            "company_id": company.id,
            "rows": payload["rows"],
            "created": payload["created"],
            "duplicates": payload["duplicates"],
            "invalid": payload["invalid"],
        })
        return {"company_id": company.id, **payload}

    def export_crm_contacts_csv(self, company_id: str) -> tuple[str, str]:
        company = self.companies.get(company_id)
        text = export_contacts_csv(self.crm, company.id)
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "-", company.name).strip("-")[:50] or company.id[:16]
        return text, f"contactos-{safe}.csv"


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _wave44_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (UnicodeDecodeError, ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _csv_body(self) -> str:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise ValueError("Content-Length is required for CSV import")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("CSV content is required")
        if length > MAX_CSV_BYTES:
            raise ValueError("CSV is larger than 2 MB")
        return self.rfile.read(length).decode("utf-8-sig")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/crm-csv.js":
            self._static(path)
            return
        parts = self._segments()
        if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3:] == ["crm", "contacts", "export"]:
            try:
                text, filename = self.server.runtime.export_crm_contacts_csv(parts[2])
                body = text.encode("utf-8")
                self._headers(
                    HTTPStatus.OK,
                    "text/csv; charset=utf-8",
                    len(body),
                    {"Content-Disposition": f'attachment; filename="{filename}"'},
                )
                self.wfile.write(body)
            except Exception as exc:
                self._wave44_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3:5] == ["crm", "contacts"] and parts[5] in {"import-preview", "import"}:
                csv_text = self._csv_body()
                if parts[5] == "import-preview":
                    self._json(self.server.runtime.preview_crm_contacts_csv(parts[2], csv_text))
                else:
                    with self.server.mutation_lock:
                        self._json(self.server.runtime.import_crm_contacts_csv(parts[2], csv_text), HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave44_error(exc)
            return
        super().do_POST()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App: {url}")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
