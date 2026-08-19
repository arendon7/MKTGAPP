from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from . import service_wave60_app as base


_OPEN_LEAD_PRIORITY = {
    "CONFLICT": 0,
    "MATCHED": 1,
    "NEW": 2,
    "UNIDENTIFIED": 3,
}
_CLOSED_OPPORTUNITY_STAGES = {"WON", "LOST"}


class AppRuntime(base.AppRuntime):
    """Wave 61 composes Inbox/Lead Intake/CRM into one local commercial desk."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def commercial_desk(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        intake = self.lead_intake_payload(company.id)
        contacts = {row.id: row for row in self.crm.list_contacts(company.id)}
        opportunities = {row.id: row for row in self.crm.list_opportunities(company.id)}
        pending_activities = [
            row for row in self.crm.list_activities(company.id)
            if row.completed_at is None
        ]

        open_leads: list[dict] = []
        converted_handoffs: list[dict] = []
        for lead in intake.get("leads") or []:
            status = str(lead.get("status") or "")
            if status in _OPEN_LEAD_PRIORITY:
                open_leads.append({
                    "priority": _OPEN_LEAD_PRIORITY[status],
                    "lead_id": lead.get("id"),
                    "status": status,
                    "display_name": lead.get("name") or lead.get("email") or lead.get("phone") or "Lead sin nombre",
                    "email": lead.get("email"),
                    "phone": lead.get("phone"),
                    "whatsapp": lead.get("whatsapp"),
                    "instagram": lead.get("instagram"),
                    "connector": lead.get("connector"),
                    "source_ref": lead.get("source_ref"),
                    "received_at": lead.get("received_at"),
                    "attribution_verified": bool(lead.get("attribution_verified")),
                    "duplicate_open_lead_count": int(lead.get("duplicate_open_lead_count") or 0),
                    "candidate_contacts": list(lead.get("candidate_contacts") or []),
                    "exact_match_count": int(lead.get("exact_match_count") or 0),
                })
                continue
            if status != "CONVERTED":
                continue

            contact_id = str(lead.get("converted_contact_id") or "") or None
            opportunity_id = str(lead.get("converted_opportunity_id") or "") or None
            contact = contacts.get(contact_id) if contact_id else None
            opportunity = opportunities.get(opportunity_id) if opportunity_id else None
            related = [
                row for row in pending_activities
                if (contact_id and row.contact_id == contact_id)
                or (opportunity_id and row.opportunity_id == opportunity_id)
            ]
            related.sort(key=lambda row: (row.due_at is None, row.due_at or row.created_at, row.id))
            next_activity = related[0] if related else None
            if opportunity is None:
                handoff_state = "NEEDS_OPPORTUNITY"
            elif opportunity.stage in _CLOSED_OPPORTUNITY_STAGES:
                handoff_state = "CLOSED"
            elif next_activity is None:
                handoff_state = "NEEDS_FOLLOWUP"
            else:
                handoff_state = "FOLLOWUP_PLANNED"
            converted_handoffs.append({
                "lead_id": lead.get("id"),
                "contact_id": contact_id,
                "contact_name": contact.name if contact is not None else lead.get("name"),
                "contact_organization": contact.organization if contact is not None else None,
                "opportunity_id": opportunity_id,
                "opportunity_title": opportunity.title if opportunity is not None else None,
                "opportunity_stage": opportunity.stage if opportunity is not None else None,
                "opportunity_value": opportunity.value if opportunity is not None else None,
                "opportunity_currency": opportunity.currency if opportunity is not None else None,
                "handoff_state": handoff_state,
                "pending_activity_count": len(related),
                "next_activity": None if next_activity is None else {
                    "id": next_activity.id,
                    "kind": next_activity.kind,
                    "summary": next_activity.summary,
                    "due_at": next_activity.due_at,
                },
            })

        open_leads.sort(key=lambda row: (
            row["priority"],
            -int(row.get("duplicate_open_lead_count") or 0),
            str(row.get("received_at") or ""),
            str(row.get("lead_id") or ""),
        ))
        handoff_priority = {
            "NEEDS_OPPORTUNITY": 0,
            "NEEDS_FOLLOWUP": 1,
            "FOLLOWUP_PLANNED": 2,
            "CLOSED": 3,
        }
        converted_handoffs.sort(key=lambda row: (
            handoff_priority.get(str(row.get("handoff_state") or ""), 9),
            str(row.get("contact_name") or "").casefold(),
            str(row.get("lead_id") or ""),
        ))

        summary = intake.get("summary") or {}
        actionable_handoffs = [row for row in converted_handoffs if row["handoff_state"] != "CLOSED"]
        return {
            "schema": "binario.marketing.commercial-desk.v1",
            "company": {"id": company.id, "name": company.name},
            "summary": {
                "open_leads": len(open_leads),
                "matched": int(summary.get("matched") or 0),
                "conflicts": int(summary.get("conflict") or 0),
                "new": int(summary.get("new") or 0),
                "unidentified": int(summary.get("unidentified") or 0),
                "converted": int(summary.get("converted") or 0),
                "contacts": len(contacts),
                "open_opportunities": sum(1 for row in opportunities.values() if row.stage not in _CLOSED_OPPORTUNITY_STAGES),
                "pending_followups": len(pending_activities),
                "handoffs_needing_action": sum(1 for row in actionable_handoffs if row["handoff_state"] in {"NEEDS_OPPORTUNITY", "NEEDS_FOLLOWUP"}),
            },
            "lead_queue": open_leads[:40],
            "handoffs": converted_handoffs[:40],
            "inbox": {
                "data_source": "BROWSER_SESSION_CACHE_ONLY",
                "manual_refresh_required": True,
                "remote_refresh_performed": False,
                "automatic_refresh": False,
            },
            "contracts": {
                "exact_identity_only": True,
                "fuzzy_name_matching": False,
                "automatic_merge": False,
                "automatic_crm_conversion": False,
                "opportunity_creation_explicit": True,
                "followup_creation_explicit": True,
            },
            "safety": {
                "remote_refresh_performed": False,
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "automatic_message_send": False,
                "automatic_crm_conversion": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/commercial-desk.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "commercial-desk":
                self._json(self.server.runtime.commercial_desk(parts[2]))
                return
        except Exception as exc:
            self._wave47_error(exc)
            return
        super().do_GET()


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
