from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .meta_credentials import MetaCredentialStore
from . import service_wave49_app as base


class AppRuntime(base.AppRuntime):
    """Wave 50 composes existing company-scoped product state into a local command center."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    @staticmethod
    def _is_due_before(value: str | None, now: datetime) -> bool:
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            return False
        return parsed.astimezone(timezone.utc) < now

    @staticmethod
    def _is_due_today(value: str | None, now: datetime) -> bool:
        if not value:
            return False
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return False
        if parsed.tzinfo is None:
            return False
        return parsed.astimezone(timezone.utc).date() == now.date()

    def marketing_command_center(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        now = datetime.now(timezone.utc)
        dashboard = self.ops_dashboard(company.id)
        creative = self.creative_context(company.id)
        social = self.social_analytics(company.id)
        workspace = self.company_workspace_summary(company.id)
        crm = self.crm.summary(company.id)
        campaigns = self.campaigns.list(company.id)
        calendar = self.ops_calendar(company.id)
        paid = self.company_paid_media(company.id)
        credential = MetaCredentialStore().status()

        publications = social.get("summary") or {}
        creative_counts = creative.get("counts") or {}
        paid_counts = {"DRAFT": 0, "REMOTE_PAUSED": 0, "CANCELLED": 0}
        for row in paid:
            status = str(row.get("status") or "")
            paid_counts[status] = paid_counts.get(status, 0) + 1

        active_campaigns = [row for row in campaigns if row.status in {"PLANNING", "READY", "IN_PROGRESS"}]
        queued = [row for row in calendar if row.get("status") == "QUEUED"]
        failed = [row for row in calendar if row.get("status") == "FAILED"]
        overdue_queue = [row for row in queued if self._is_due_before(row.get("scheduled_for"), now)]
        today_queue = [row for row in queued if self._is_due_today(row.get("scheduled_for"), now)]
        pending_activities = [row for row in self.crm.list_activities(company.id) if row.completed_at is None]
        overdue_activities = [row for row in pending_activities if self._is_due_before(row.due_at, now)]
        today_activities = [row for row in pending_activities if self._is_due_today(row.due_at, now)]

        readiness_steps = [
            {"id": "workspace", "label": "Workspace de creación", "ready": bool(workspace.get("project_id")), "view": "video"},
            {"id": "meta", "label": "Conexión Meta", "ready": bool(credential.configured), "view": "companies"},
            {"id": "facebook", "label": "Facebook Page", "ready": bool(company.facebook_page_id), "view": "companies"},
            {"id": "instagram", "label": "Instagram profesional", "ready": bool(company.instagram_id), "view": "companies"},
            {"id": "ads", "label": "Cuenta publicitaria", "ready": bool(company.ad_account_id), "view": "companies"},
            {"id": "campaign", "label": "Campaña de marketing", "ready": bool(campaigns), "view": "campaigns"},
            {"id": "creative", "label": "Creative Studio", "ready": any(row.get("creative") for row in creative.get("items") or []), "view": "content"},
            {"id": "crm", "label": "CRM con contactos", "ready": bool(crm.get("contacts")), "view": "crm"},
        ]
        readiness_ready = sum(1 for row in readiness_steps if row["ready"])

        priorities: list[dict] = []
        def priority(level: int, kind: str, title: str, detail: str, view: str, *, entity_id: str | None = None) -> None:
            priorities.append({
                "level": level,
                "kind": kind,
                "title": title,
                "detail": detail,
                "view": view,
                "entity_id": entity_id,
            })

        for row in failed[:4]:
            priority(0, "publication_failed", "Publicación con error", str(row.get("message") or row.get("error") or "Revisar publicación"), "calendar", entity_id=row.get("id"))
        for row in overdue_queue[:4]:
            priority(1, "publication_overdue", "Programación vencida", str(row.get("message") or "Revisar fecha y estado"), "calendar", entity_id=row.get("id"))
        for row in overdue_activities[:4]:
            priority(2, "crm_overdue", "Seguimiento CRM vencido", row.summary or "Completar o reprogramar seguimiento", "crm", entity_id=row.id)

        unprofiled = [row for row in creative.get("items") or [] if row.get("effective_stage") == "UNPROFILED"]
        ready_without_campaign = [
            row for row in creative.get("items") or []
            if row.get("effective_stage") == "READY" and not (row.get("creative") or {}).get("campaign_id")
        ]
        if unprofiled:
            priority(5, "creative_unprofiled", f"{len(unprofiled)} piezas sin brief", "Define objetivo, copy, campaña y canales para convertir archivos en activos de marketing.", "content")
        if ready_without_campaign:
            priority(5, "creative_campaign", f"{len(ready_without_campaign)} piezas listas sin campaña", "Conecta la pieza a una campaña antes de distribuirla para conservar trazabilidad.", "content")

        campaign_without_media = [row for row in active_campaigns if not row.media_ids]
        if campaign_without_media:
            priority(6, "campaign_media", f"{len(campaign_without_media)} campañas sin creativo", "Añade activos desde Creative Studio para poder llevar la campaña a calendario o pauta.", "campaigns")
        if paid_counts.get("DRAFT", 0):
            priority(7, "paid_draft", f"{paid_counts['DRAFT']} planes de pauta en borrador", "Revisa targeting, presupuesto y creativo antes de crear la jerarquía PAUSED en Meta.", "pauta")

        for step in readiness_steps:
            if not step["ready"]:
                priority(9, f"setup_{step['id']}", f"Completar: {step['label']}", "Este componente todavía limita el flujo integral de la empresa.", step["view"])

        priorities.sort(key=lambda row: (row["level"], row["kind"], row.get("entity_id") or ""))
        priorities = priorities[:12]

        campaign_rows = []
        for row in active_campaigns[:6]:
            campaign_rows.append({
                "id": row.id,
                "name": row.name,
                "objective": row.objective,
                "status": row.status,
                "start_at": row.start_at,
                "end_at": row.end_at,
                "audience": len(row.audience_contact_ids),
                "media": len(row.media_ids),
                "publications": len(row.publication_ids),
                "channels": list(row.channels),
            })

        return {
            "schema": "binario.marketing.command-center.v1",
            "generated_at": now.isoformat(),
            "company": asdict(company),
            "readiness": {
                "ready": readiness_ready,
                "total": len(readiness_steps),
                "percent": round(readiness_ready * 100 / len(readiness_steps)),
                "steps": readiness_steps,
            },
            "flow": {
                "campaigns_active": len(active_campaigns),
                "creatives_production": (creative_counts.get("BRIEF", 0) + creative_counts.get("DRAFT", 0)),
                "creatives_ready": creative_counts.get("READY", 0),
                "scheduled": len(queued),
                "published": publications.get("published", 0),
                "paid_plans": len(paid),
                "paid_remote_paused": paid_counts.get("REMOTE_PAUSED", 0),
                "crm_open_opportunities": crm.get("opportunities_open", 0),
            },
            "attention": {
                "total": len(failed) + len(overdue_queue) + len(overdue_activities),
                "publication_failed": len(failed),
                "publication_overdue": len(overdue_queue),
                "crm_overdue": len(overdue_activities),
                "publication_today": len(today_queue),
                "crm_today": len(today_activities),
            },
            "creative": {
                "total": len(creative.get("items") or []),
                "counts": creative_counts,
                "unprofiled": len(unprofiled),
            },
            "campaigns": campaign_rows,
            "paid_media": {
                "total": len(paid),
                "counts": paid_counts,
            },
            "crm": crm,
            "publications": publications,
            "workspace": workspace,
            "priorities": priorities,
            "safety": {
                "remote_refresh_performed": False,
                "provider_mutation_performed": False,
                "meta_connected": bool(credential.configured),
            },
            "legacy_dashboard": dashboard,
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/command-center.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "command-center":
                self._json(self.server.runtime.marketing_command_center(parts[2]))
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
