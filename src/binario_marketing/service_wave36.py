from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .audience_store import AudienceStore
from .crm_import import ContactCSVImporter, MAX_CSV_BYTES
from . import service_wave35 as base


class AppRuntime(base.AppRuntime):
    """Wave 36 adds reusable CRM audiences and deterministic CSV contact import."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.audiences = AudienceStore(runtime.data_root / "State" / "audiences")
        return runtime

    def ops_dashboard(self, company_id: str | None = None) -> dict:
        payload = super().ops_dashboard(company_id)
        payload["audiences"] = self.audiences.summary(company_id)
        return payload

    def audience_summary(self, company_id: str | None = None) -> dict:
        if company_id:
            self.companies.get(company_id)
        return self.audiences.summary(company_id)

    def _validate_audience_contacts(self, company_id: str, contact_ids) -> list[str]:
        company = self.companies.get(company_id)
        if contact_ids in (None, ""):
            return []
        if not isinstance(contact_ids, (list, tuple)):
            raise ValueError("contact_ids must be an array")
        result: list[str] = []
        for raw in contact_ids:
            contact_id = str(raw or "").strip()
            row = self.crm.get_contact(contact_id)
            if row.company_id != company.id:
                raise KeyError(contact_id)
            if row.id not in result:
                result.append(row.id)
        return result

    def _audience_payload(self, row) -> dict:
        payload = asdict(row)
        contacts = []
        for contact_id in row.contact_ids:
            contact = self.crm.get_contact(contact_id)
            if contact.company_id != row.company_id:
                raise KeyError(contact_id)
            contacts.append(asdict(contact))
        payload["contacts"] = contacts
        payload["member_count"] = len(contacts)
        payload["email_reachable"] = sum(1 for contact in contacts if contact.get("email"))
        payload["whatsapp_reachable"] = sum(1 for contact in contacts if contact.get("whatsapp") or contact.get("phone"))
        return payload

    def audiences_payload(self, company_id: str) -> list[dict]:
        company = self.companies.get(company_id)
        return [self._audience_payload(row) for row in self.audiences.list(company.id)]

    def audience_detail(self, company_id: str, audience_id: str) -> dict:
        company = self.companies.get(company_id)
        return self._audience_payload(self.audiences.get_for_company(company.id, audience_id))

    def create_audience(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("audience payload must be an object")
        clean = dict(payload)
        clean["contact_ids"] = self._validate_audience_contacts(company.id, clean.get("contact_ids"))
        row = self.audiences.create(company.id, clean)
        self.workspace.registries.timeline.append("crm.audience.created", {
            "company_id": company.id,
            "audience_id": row.id,
            "name": row.name,
            "member_count": len(row.contact_ids),
        })
        return self._audience_payload(row)

    def update_audience(self, company_id: str, audience_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        self.audiences.get_for_company(company.id, audience_id)
        if not isinstance(payload, dict):
            raise ValueError("audience payload must be an object")
        clean = dict(payload)
        if "contact_ids" in clean:
            clean["contact_ids"] = self._validate_audience_contacts(company.id, clean.get("contact_ids"))
        row = self.audiences.update(company.id, audience_id, clean)
        self.workspace.registries.timeline.append("crm.audience.updated", {
            "company_id": company.id,
            "audience_id": row.id,
            "member_count": len(row.contact_ids),
        })
        return self._audience_payload(row)

    def delete_audience(self, company_id: str, audience_id: str) -> dict:
        company = self.companies.get(company_id)
        row = self.audiences.delete(company.id, audience_id)
        self.workspace.registries.timeline.append("crm.audience.deleted", {
            "company_id": company.id,
            "audience_id": row.id,
        })
        return asdict(row)

    def import_contacts_csv(self, company_id: str, content: bytes, *, strategy: str = "skip") -> dict:
        company = self.companies.get(company_id)
        report = ContactCSVImporter(self.crm).import_bytes(company.id, content, strategy=strategy)
        self.workspace.registries.timeline.append("crm.contacts.imported", {
            "company_id": company.id,
            "strategy": report["strategy"],
            "rows": report["rows"],
            "created": report["created"],
            "updated": report["updated"],
            "skipped": report["skipped"],
            "error_count": report["error_count"],
        })
        return report


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Audience/CSV extension. No route sends provider messages."""

    def _wave36_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/audiences.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "audiences", "summary"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.audience_summary(company_id))
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "audiences":
                self._json(self.server.runtime.audiences_payload(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "audiences":
                self._json(self.server.runtime.audience_detail(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave36_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "audiences":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_audience(parts[2], self._body()), HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["contacts", "import"]:
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    raise ValueError("Content-Length is required for CSV import")
                try:
                    length = int(raw_length)
                except ValueError as exc:
                    raise ValueError("invalid Content-Length") from exc
                if length <= 0 or length > MAX_CSV_BYTES:
                    raise ValueError("CSV import must be between 1 byte and 10 MiB")
                content = self.rfile.read(length)
                if len(content) != length:
                    raise ValueError("CSV body ended before Content-Length")
                query = parse_qs(urlparse(self.path).query)
                strategy = (query.get("strategy") or ["skip"])[0]
                with self.server.mutation_lock:
                    self._json(self.server.runtime.import_contacts_csv(parts[2], content, strategy=strategy))
                return
        except Exception as exc:
            self._wave36_error(exc)
            return
        super().do_POST()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "audiences":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.update_audience(parts[2], parts[4], self._body()))
                return
        except Exception as exc:
            self._wave36_error(exc)
            return
        super().do_PATCH()

    def do_DELETE(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "audiences":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.delete_audience(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave36_error(exc)
            return
        super().do_DELETE()


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
