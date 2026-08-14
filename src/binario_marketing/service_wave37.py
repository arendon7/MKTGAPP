from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .contactability_store import CONTACTABILITY_CHANNELS, ContactabilityStore
from . import service_wave36 as base


class AppRuntime(base.AppRuntime):
    """Wave 37 adds current per-channel contactability without enabling any outbound provider."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.contactability = ContactabilityStore(runtime.data_root / "State" / "contactability")
        return runtime

    def _contact_for_company(self, company_id: str, contact_id: str):
        company = self.companies.get(company_id)
        contact = self.crm.get_contact(contact_id)
        if contact.company_id != company.id:
            raise KeyError(contact_id)
        return company, contact

    @staticmethod
    def _has_destination(contact, channel: str) -> bool:
        if channel == "email":
            return bool(contact.email)
        if channel == "whatsapp":
            return bool(contact.whatsapp or contact.phone)
        return False

    def contactability_payload(self, company_id: str, contact_id: str) -> dict:
        company, contact = self._contact_for_company(company_id, contact_id)
        channels = {}
        for channel in CONTACTABILITY_CHANNELS:
            row = self.contactability.get(company.id, contact.id, channel)
            payload = asdict(row)
            payload["has_destination"] = self._has_destination(contact, channel)
            payload["eligible"] = bool(payload["has_destination"] and row.status == "OPTED_IN")
            channels[channel] = payload
        return {
            "company_id": company.id,
            "contact_id": contact.id,
            "contact_name": contact.name,
            "channels": channels,
        }

    def set_contactability(self, company_id: str, contact_id: str, channel: str, payload: dict) -> dict:
        company, contact = self._contact_for_company(company_id, contact_id)
        before = self.contactability.get(company.id, contact.id, channel)
        row = self.contactability.set(company.id, contact.id, channel, payload)
        self.workspace.registries.timeline.append("crm.contactability.updated", {
            "company_id": company.id,
            "contact_id": contact.id,
            "channel": row.channel,
            "status_from": before.status,
            "status_to": row.status,
            "source": row.source,
            "captured_at": row.captured_at,
        })
        return self.contactability_payload(company.id, contact.id)["channels"][row.channel]

    def reset_contactability(self, company_id: str, contact_id: str, channel: str) -> dict:
        company, contact = self._contact_for_company(company_id, contact_id)
        before = self.contactability.get(company.id, contact.id, channel)
        row = self.contactability.reset(company.id, contact.id, channel)
        self.workspace.registries.timeline.append("crm.contactability.reset", {
            "company_id": company.id,
            "contact_id": contact.id,
            "channel": row.channel,
            "status_from": before.status,
            "status_to": "UNKNOWN",
        })
        return self.contactability_payload(company.id, contact.id)["channels"][row.channel]

    def _contactability_counts(self, company_id: str, contacts) -> dict:
        result = {}
        for channel in CONTACTABILITY_CHANNELS:
            counts = {
                "contacts": len(contacts),
                "has_destination": 0,
                "opted_in": 0,
                "unknown": 0,
                "opted_out": 0,
                "eligible": 0,
                "suppressed": 0,
            }
            for contact in contacts:
                has_destination = self._has_destination(contact, channel)
                row = self.contactability.get(company_id, contact.id, channel)
                if has_destination:
                    counts["has_destination"] += 1
                if row.status == "OPTED_IN":
                    counts["opted_in"] += 1
                elif row.status == "OPTED_OUT":
                    counts["opted_out"] += 1
                else:
                    counts["unknown"] += 1
                if has_destination and row.status == "OPTED_IN":
                    counts["eligible"] += 1
                elif has_destination:
                    counts["suppressed"] += 1
            result[channel] = counts
        return result

    def contactability_summary(self, company_id: str | None = None) -> dict:
        if company_id:
            company = self.companies.get(company_id)
            contacts = self.crm.list_contacts(company.id)
            return {
                "company_id": company.id,
                "contacts": len(contacts),
                "channels": self._contactability_counts(company.id, contacts),
            }
        contacts = self.crm.list_contacts()
        by_company = {}
        for contact in contacts:
            by_company.setdefault(contact.company_id, []).append(contact)
        combined = {
            channel: {key: 0 for key in ("contacts", "has_destination", "opted_in", "unknown", "opted_out", "eligible", "suppressed")}
            for channel in CONTACTABILITY_CHANNELS
        }
        for current_company, rows in by_company.items():
            counts = self._contactability_counts(current_company, rows)
            for channel in CONTACTABILITY_CHANNELS:
                for key, value in counts[channel].items():
                    combined[channel][key] += value
        return {"company_id": None, "contacts": len(contacts), "channels": combined}

    def ops_dashboard(self, company_id: str | None = None) -> dict:
        payload = super().ops_dashboard(company_id)
        payload["contactability"] = self.contactability_summary(company_id)
        return payload

    def _audience_payload(self, row) -> dict:
        payload = super()._audience_payload(row)
        contacts = [self.crm.get_contact(contact_id) for contact_id in row.contact_ids]
        payload["contactability"] = self._contactability_counts(row.company_id, contacts)
        return payload

    def _channel_readiness(self, company, campaign) -> dict:
        readiness = super()._channel_readiness(company, campaign)
        contacts = [self.crm.get_contact(contact_id) for contact_id in campaign.audience_contact_ids]
        counts = self._contactability_counts(company.id, contacts)
        for channel in CONTACTABILITY_CHANNELS:
            readiness[channel].update(counts[channel])
            readiness[channel]["audience_reachable"] = counts[channel]["has_destination"]
            readiness[channel]["send_gate"] = "OPTED_IN_REQUIRED"
            readiness[channel]["planned_only"] = True
            readiness[channel]["provider_configured"] = False
        return readiness


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Contactability API/static extension. It contains no outbound-send route."""

    def _wave37_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/contactability.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "contactability", "summary"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.contactability_summary(company_id))
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "contacts" and parts[5] == "contactability":
                self._json(self.server.runtime.contactability_payload(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave37_error(exc)
            return
        super().do_GET()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 7 and parts[:2] == ["api", "companies"] and parts[3] == "contacts" and parts[5] == "contactability":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.set_contactability(parts[2], parts[4], parts[6], self._body()))
                return
        except Exception as exc:
            self._wave37_error(exc)
            return
        super().do_PATCH()

    def do_DELETE(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 7 and parts[:2] == ["api", "companies"] and parts[3] == "contacts" and parts[5] == "contactability":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.reset_contactability(parts[2], parts[4], parts[6]))
                return
        except Exception as exc:
            self._wave37_error(exc)
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
