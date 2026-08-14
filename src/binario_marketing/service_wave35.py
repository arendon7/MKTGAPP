from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .campaign_store import CampaignStore
from . import service_wave34 as base


class AppRuntime(base.AppRuntime):
    """Wave 35 joins CRM, content and publications into company-scoped campaign plans."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.campaigns = CampaignStore(runtime.data_root / "State" / "campaigns")
        return runtime

    def ops_dashboard(self, company_id: str | None = None) -> dict:
        payload = super().ops_dashboard(company_id)
        payload["campaigns"] = self.campaigns.summary(company_id)
        return payload

    def campaign_summary(self, company_id: str | None = None) -> dict:
        if company_id:
            self.companies.get(company_id)
        return self.campaigns.summary(company_id)

    def campaigns_payload(self, company_id: str) -> list[dict]:
        self.companies.get(company_id)
        return [self._campaign_payload(row) for row in self.campaigns.list(company_id)]

    def _validate_campaign_references(self, company_id: str, payload: dict) -> None:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("campaign payload must be an object")
        if "audience_contact_ids" in payload:
            values = payload.get("audience_contact_ids") or []
            if not isinstance(values, (list, tuple)):
                raise ValueError("audience_contact_ids must be an array")
            for contact_id in values:
                row = self.crm.get_contact(str(contact_id))
                if row.company_id != company.id:
                    raise KeyError(contact_id)
        if "media_ids" in payload:
            values = payload.get("media_ids") or []
            if not isinstance(values, (list, tuple)):
                raise ValueError("media_ids must be an array")
            for media_id in values:
                self.company_media.get_for_company(company.id, str(media_id))
        if "publication_ids" in payload:
            values = payload.get("publication_ids") or []
            if not isinstance(values, (list, tuple)):
                raise ValueError("publication_ids must be an array")
            for publication_id in values:
                row = self.social.get(str(publication_id))
                if row.project_id != company.id:
                    raise KeyError(publication_id)

    def _channel_readiness(self, company, campaign) -> dict:
        contacts = [self.crm.get_contact(contact_id) for contact_id in campaign.audience_contact_ids]
        return {
            "facebook_page": {
                "selected": "facebook_page" in campaign.channels,
                "provider_configured": bool(company.facebook_page_id),
                "label": company.facebook_page_name or company.facebook_page_id,
            },
            "instagram": {
                "selected": "instagram" in campaign.channels,
                "provider_configured": bool(company.instagram_id),
                "label": f"@{company.instagram_username}" if company.instagram_username else company.instagram_id,
            },
            "email": {
                "selected": "email" in campaign.channels,
                "provider_configured": False,
                "audience_reachable": sum(1 for row in contacts if row.email),
                "planned_only": True,
            },
            "whatsapp": {
                "selected": "whatsapp" in campaign.channels,
                "provider_configured": False,
                "audience_reachable": sum(1 for row in contacts if row.whatsapp or row.phone),
                "planned_only": True,
            },
        }

    def _campaign_payload(self, row) -> dict:
        company = self.companies.get(row.company_id)
        payload = asdict(row)
        payload["readiness"] = self._channel_readiness(company, row)
        return payload

    def campaign_detail(self, company_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        row = self.campaigns.get_for_company(company.id, campaign_id)
        contacts = [asdict(self.crm.get_contact(contact_id)) for contact_id in row.audience_contact_ids]
        media = [asdict(self.company_media.get_for_company(company.id, media_id)) for media_id in row.media_ids]
        publications = []
        for publication_id in row.publication_ids:
            publication = self.social.get(publication_id)
            if publication.project_id != company.id:
                raise KeyError(publication_id)
            publications.append(asdict(publication))
        return {
            "campaign": self._campaign_payload(row),
            "audience": contacts,
            "media": media,
            "publications": publications,
        }

    def create_campaign(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        self._validate_campaign_references(company.id, payload)
        row = self.campaigns.create(company.id, payload)
        self.workspace.registries.timeline.append("campaign.created", {
            "company_id": company.id,
            "campaign_id": row.id,
            "name": row.name,
            "objective": row.objective,
            "status": row.status,
            "channels": list(row.channels),
        })
        return self._campaign_payload(row)

    def update_campaign(self, company_id: str, campaign_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        before = self.campaigns.get_for_company(company.id, campaign_id)
        self._validate_campaign_references(company.id, payload)
        row = self.campaigns.update(company.id, campaign_id, payload)
        self.workspace.registries.timeline.append("campaign.updated", {
            "company_id": company.id,
            "campaign_id": row.id,
            "status_from": before.status,
            "status_to": row.status,
            "channels": list(row.channels),
        })
        return self._campaign_payload(row)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Campaign API/static extension. It has no provider mutation routes."""

    def _wave35_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/campaigns.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "campaigns", "summary"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.campaign_summary(company_id))
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "campaigns":
                self._json(self.server.runtime.campaigns_payload(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "campaigns":
                self._json(self.server.runtime.campaign_detail(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave35_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "campaigns":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_campaign(parts[2], self._body()), HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave35_error(exc)
            return
        super().do_POST()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "campaigns":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.update_campaign(parts[2], parts[4], self._body()))
                return
        except Exception as exc:
            self._wave35_error(exc)
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
