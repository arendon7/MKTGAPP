from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave59_app as base


class AppRuntime(base.AppRuntime):
    """Wave 60 composes daily local work without adding provider or cloud side effects."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def daily_workdesk(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        now = datetime.now(timezone.utc)
        command = self.marketing_command_center(company.id)
        calendar = self.ops_calendar(company.id)
        contacts = {row.id: row for row in self.crm.list_contacts(company.id)}
        opportunities = {row.id: row for row in self.crm.list_opportunities(company.id)}
        activities = [row for row in self.crm.list_activities(company.id) if row.completed_at is None]

        failed_publications = [row for row in calendar if row.get("status") == "FAILED"]
        queued_publications = [row for row in calendar if row.get("status") == "QUEUED"]
        overdue_publications = [row for row in queued_publications if self._is_due_before(row.get("scheduled_for"), now)]
        overdue_publication_ids = {str(row.get("id") or "") for row in overdue_publications}
        today_publications = [
            row for row in queued_publications
            if self._is_due_today(row.get("scheduled_for"), now)
            and str(row.get("id") or "") not in overdue_publication_ids
        ]

        overdue_activities = [row for row in activities if row.due_at and self._is_due_before(row.due_at, now)]
        overdue_activity_ids = {row.id for row in overdue_activities}
        today_activities = [
            row for row in activities
            if row.due_at and self._is_due_today(row.due_at, now) and row.id not in overdue_activity_ids
        ]
        unscheduled_activities = [row for row in activities if not row.due_at]

        def activity_context(row) -> dict:
            contact_id = row.contact_id
            opportunity = opportunities.get(row.opportunity_id) if row.opportunity_id else None
            if not contact_id and opportunity is not None:
                contact_id = opportunity.contact_id
            contact = contacts.get(contact_id) if contact_id else None
            return {
                "activity_id": row.id,
                "contact_id": contact_id,
                "contact_name": contact.name if contact is not None else None,
                "opportunity_id": row.opportunity_id,
                "opportunity_title": opportunity.title if opportunity is not None else None,
                "kind": row.kind,
                "summary": row.summary,
                "due_at": row.due_at,
            }

        queue: list[dict] = []

        def add_item(
            priority: int,
            kind: str,
            title: str,
            detail: str,
            view: str,
            *,
            due_at: str | None = None,
            entity_id: str | None = None,
            contact_id: str | None = None,
            opportunity_id: str | None = None,
            tab: str | None = None,
        ) -> None:
            queue.append({
                "priority": priority,
                "kind": kind,
                "title": title,
                "detail": detail,
                "view": view,
                "tab": tab,
                "due_at": due_at,
                "entity_id": entity_id,
                "contact_id": contact_id,
                "opportunity_id": opportunity_id,
            })

        for row in failed_publications:
            add_item(
                0,
                "publication_failed",
                "Publicación con error",
                str(row.get("message") or row.get("error") or "Revisar publicación"),
                "calendar",
                due_at=row.get("scheduled_for") or row.get("updated_at"),
                entity_id=row.get("id"),
            )
        for row in overdue_publications:
            add_item(
                1,
                "publication_overdue",
                "Programación vencida",
                str(row.get("message") or "Revisar fecha y estado"),
                "calendar",
                due_at=row.get("scheduled_for"),
                entity_id=row.get("id"),
            )
        for row in overdue_activities:
            ctx = activity_context(row)
            add_item(
                2,
                "crm_overdue",
                "Seguimiento vencido",
                row.summary,
                "crm",
                tab="followups",
                due_at=row.due_at,
                entity_id=row.id,
                contact_id=ctx["contact_id"],
                opportunity_id=row.opportunity_id,
            )
        for row in today_activities:
            ctx = activity_context(row)
            add_item(
                3,
                "crm_today",
                "Seguimiento de hoy",
                row.summary,
                "crm",
                tab="followups",
                due_at=row.due_at,
                entity_id=row.id,
                contact_id=ctx["contact_id"],
                opportunity_id=row.opportunity_id,
            )
        for row in today_publications:
            add_item(
                4,
                "publication_today",
                "Publicación de hoy",
                str(row.get("message") or "Publicación programada"),
                "calendar",
                due_at=row.get("scheduled_for"),
                entity_id=row.get("id"),
            )
        for row in unscheduled_activities:
            ctx = activity_context(row)
            add_item(
                5,
                "crm_unscheduled",
                "Seguimiento sin fecha",
                row.summary,
                "crm",
                tab="followups",
                due_at=None,
                entity_id=row.id,
                contact_id=ctx["contact_id"],
                opportunity_id=row.opportunity_id,
            )

        queue.sort(key=lambda row: (row["priority"], row.get("due_at") or "", row.get("entity_id") or ""))
        queue = queue[:20]

        crm_rows = [activity_context(row) for row in activities]
        crm_rows.sort(key=lambda row: (row.get("due_at") is None, row.get("due_at") or "", row["activity_id"]))
        product_gaps = [
            row for row in command.get("priorities") or []
            if int(row.get("level") or 0) >= 5
        ][:5]

        return {
            "schema": "binario.marketing.workdesk.v1",
            "generated_at": now.isoformat(),
            "company": {"id": company.id, "name": company.name},
            "next_action": queue[0] if queue else None,
            "queue": queue,
            "summary": {
                "attention": len(failed_publications) + len(overdue_publications) + len(overdue_activities),
                "today": len(today_publications) + len(today_activities),
                "unscheduled": len(unscheduled_activities),
                "queue_total": len(queue),
            },
            "crm": {
                "pending": len(activities),
                "overdue": len(overdue_activities),
                "today": len(today_activities),
                "unscheduled": len(unscheduled_activities),
                "open_opportunities": int((command.get("crm") or {}).get("opportunities_open") or 0),
                "activities": crm_rows[:12],
            },
            "publications": {
                "failed": len(failed_publications),
                "overdue": len(overdue_publications),
                "today": len(today_publications),
            },
            "inbox": {
                "view": "inbox",
                "manual_refresh_required": True,
                "remote_refresh_performed": False,
                "automatic_refresh": False,
            },
            "product_gaps": product_gaps,
            "safety": {
                "remote_refresh_performed": False,
                "provider_mutation_performed": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/workdesk.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "workdesk":
                self._json(self.server.runtime.daily_workdesk(parts[2]))
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
