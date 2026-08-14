from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .crm_store import CRMStore
from . import service_wave31 as base


class AppRuntime(base.AppRuntime):
    """Wave 32 adds a practical company-scoped CRM to the certified operations runtime."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.crm = CRMStore(runtime.data_root / "State" / "crm")
        return runtime

    def ops_dashboard(self, company_id: str | None = None) -> dict:
        payload = super().ops_dashboard(company_id)
        payload["crm"] = self.crm.summary(company_id)
        return payload

    def crm_summary(self, company_id: str | None = None) -> dict:
        if company_id:
            self.companies.get(company_id)
        return self.crm.summary(company_id)

    def contacts_payload(self, company_id: str) -> list[dict]:
        self.companies.get(company_id)
        return [asdict(row) for row in self.crm.list_contacts(company_id)]

    def contact_detail(self, company_id: str, contact_id: str) -> dict:
        self.companies.get(company_id)
        return self.crm.contact_detail(company_id, contact_id)

    def create_contact(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        row = self.crm.create_contact(company.id, payload)
        self.workspace.registries.timeline.append("crm.contact.created", {
            "company_id": company.id,
            "contact_id": row.id,
            "name": row.name,
        })
        return asdict(row)

    def update_contact(self, company_id: str, contact_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        row = self.crm.update_contact(company.id, contact_id, payload)
        self.workspace.registries.timeline.append("crm.contact.updated", {
            "company_id": company.id,
            "contact_id": row.id,
        })
        return asdict(row)

    def opportunities_payload(self, company_id: str) -> list[dict]:
        self.companies.get(company_id)
        return [asdict(row) for row in self.crm.list_opportunities(company_id)]

    def create_opportunity(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        row = self.crm.create_opportunity(company.id, payload)
        self.workspace.registries.timeline.append("crm.opportunity.created", {
            "company_id": company.id,
            "opportunity_id": row.id,
            "contact_id": row.contact_id,
            "stage": row.stage,
            "value": row.value,
            "currency": row.currency,
        })
        return asdict(row)

    def update_opportunity(self, company_id: str, opportunity_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        before = self.crm.get_opportunity(opportunity_id)
        if before.company_id != company.id:
            raise KeyError(opportunity_id)
        row = self.crm.update_opportunity(company.id, opportunity_id, payload)
        self.workspace.registries.timeline.append("crm.opportunity.updated", {
            "company_id": company.id,
            "opportunity_id": row.id,
            "stage_from": before.stage,
            "stage_to": row.stage,
            "value": row.value,
            "currency": row.currency,
        })
        return asdict(row)

    def activities_payload(self, company_id: str, *, contact_id: str | None = None, opportunity_id: str | None = None) -> list[dict]:
        self.companies.get(company_id)
        return [asdict(row) for row in self.crm.list_activities(company_id, contact_id=contact_id, opportunity_id=opportunity_id)]

    def create_activity(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        row = self.crm.create_activity(company.id, payload)
        self.workspace.registries.timeline.append("crm.activity.created", {
            "company_id": company.id,
            "activity_id": row.id,
            "contact_id": row.contact_id,
            "opportunity_id": row.opportunity_id,
            "kind": row.kind,
            "due_at": row.due_at,
        })
        return asdict(row)

    def complete_activity(self, company_id: str, activity_id: str) -> dict:
        company = self.companies.get(company_id)
        row = self.crm.complete_activity(company.id, activity_id)
        self.workspace.registries.timeline.append("crm.activity.completed", {
            "company_id": company.id,
            "activity_id": row.id,
            "completed_at": row.completed_at,
        })
        return asdict(row)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """CRM API/static extension; every Wave 31 and legacy route delegates unchanged."""

    def _wave32_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/crm.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "crm", "summary"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.crm_summary(company_id))
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "contacts":
                self._json(self.server.runtime.contacts_payload(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "contacts":
                self._json(self.server.runtime.contact_detail(parts[2], parts[4]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "opportunities":
                self._json(self.server.runtime.opportunities_payload(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "activities":
                query = parse_qs(urlparse(self.path).query)
                contact_id = (query.get("contact_id") or [None])[0]
                opportunity_id = (query.get("opportunity_id") or [None])[0]
                self._json(self.server.runtime.activities_payload(parts[2], contact_id=contact_id, opportunity_id=opportunity_id))
                return
        except Exception as exc:
            self._wave32_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "contacts":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_contact(parts[2], self._body()), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "opportunities":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_opportunity(parts[2], self._body()), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "activities":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_activity(parts[2], self._body()), HTTPStatus.CREATED)
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "activities" and parts[5] == "complete":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.complete_activity(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave32_error(exc)
            return
        super().do_POST()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "contacts":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.update_contact(parts[2], parts[4], self._body()))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "opportunities":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.update_opportunity(parts[2], parts[4], self._body()))
                return
        except Exception as exc:
            self._wave32_error(exc)
            return
        super().do_PATCH()


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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
