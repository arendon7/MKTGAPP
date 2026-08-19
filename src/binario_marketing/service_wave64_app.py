from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_wave63_app as base


_ORGANIC_CHANNELS = {"facebook_page", "instagram"}
_TERMINAL_CAMPAIGN_STATUSES = {"COMPLETED", "ARCHIVED"}
_READY_CREATIVE_STAGES = {"READY", "SCHEDULED", "PUBLISHED", "PAID"}


def _count_status(rows: list[dict], key: str = "status") -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "UNKNOWN").upper()
        counts[value] = counts.get(value, 0) + 1
    return counts


class AppRuntime(base.AppRuntime):
    """Wave 64 projects campaigns into a deterministic local execution workspace."""

    def campaign_execution_workspace(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        campaigns = list(self.campaigns.list(company.id))
        creative_rows = self.company_creatives_payload(company.id)
        paid_rows = self.company_paid_media(company.id)

        creative_by_media = {row["media"]["id"]: row for row in creative_rows}
        paid_by_id = {row["id"]: row for row in paid_rows}
        cards: list[dict] = []

        for campaign in campaigns:
            media_ids = set(campaign.media_ids)
            linked_creatives = [
                row for row in creative_rows
                if row["media"]["id"] in media_ids
                or (row.get("creative") and row["creative"].get("campaign_id") == campaign.id)
            ]
            for row in linked_creatives:
                media_ids.add(row["media"]["id"])

            publication_ids = set(campaign.publication_ids)
            paid_ids: set[str] = set()
            for row in linked_creatives:
                creative = row.get("creative") or {}
                publication_ids.update(creative.get("publication_ids") or [])
                paid_ids.update(creative.get("paid_media_ids") or [])

            publications: list[dict] = []
            for publication_id in sorted(publication_ids):
                try:
                    row = self.social.get(publication_id)
                except KeyError:
                    continue
                if row.project_id != company.id:
                    continue
                publications.append(asdict(row))

            linked_paid = [
                row for row in paid_rows
                if row.get("plan") and row["plan"].get("campaign_id") == campaign.id
            ]
            for draft_id in sorted(paid_ids):
                row = paid_by_id.get(draft_id)
                if row is not None and all(existing["id"] != draft_id for existing in linked_paid):
                    linked_paid.append(row)

            creative_counts = _count_status(linked_creatives, "effective_stage")
            publication_counts = _count_status(publications)
            paid_counts = _count_status(linked_paid)
            ready_creatives = sum(creative_counts.get(stage, 0) for stage in _READY_CREATIVE_STAGES)
            organic_selected = bool(set(campaign.channels) & _ORGANIC_CHANNELS)
            planned_only_channels = [channel for channel in campaign.channels if channel not in _ORGANIC_CHANNELS]
            failed_publications = publication_counts.get("FAILED", 0)
            queued_publications = publication_counts.get("QUEUED", 0)
            published_publications = publication_counts.get("PUBLISHED", 0)
            draft_publications = publication_counts.get("DRAFT", 0)
            paid_drafts = paid_counts.get("DRAFT", 0)
            paid_remote_paused = paid_counts.get("REMOTE_PAUSED", 0)

            steps = [
                {
                    "code": "PLAN",
                    "label": "Plan",
                    "state": "READY" if campaign.channels else "NEEDS_ACTION",
                    "detail": f"{len(campaign.channels)} canales definidos" if campaign.channels else "Faltan canales",
                },
                {
                    "code": "CREATIVE",
                    "label": "Creativos",
                    "state": "READY" if ready_creatives else "NEEDS_ACTION",
                    "detail": f"{ready_creatives} listos de {len(linked_creatives)}" if linked_creatives else "Sin piezas vinculadas",
                },
                {
                    "code": "ORGANIC",
                    "label": "Orgánico",
                    "state": (
                        "ACTIVE" if published_publications or queued_publications
                        else "READY" if draft_publications
                        else "NEEDS_ACTION" if organic_selected
                        else "NOT_REQUIRED"
                    ),
                    "detail": (
                        f"{published_publications} publicadas · {queued_publications} programadas · {draft_publications} borradores"
                        if publications else ("Sin publicación preparada" if organic_selected else "No seleccionado")
                    ),
                },
                {
                    "code": "PAID",
                    "label": "Pauta",
                    "state": "ACTIVE" if paid_remote_paused else "READY" if linked_paid else "OPTIONAL",
                    "detail": f"{len(linked_paid)} planes · {paid_remote_paused} remotos PAUSED" if linked_paid else "Opcional",
                },
                {
                    "code": "LEARNING",
                    "label": "Resultados",
                    "state": "READY" if published_publications or paid_remote_paused else "WAITING",
                    "detail": "Hay distribución para medir" if published_publications or paid_remote_paused else "Esperando distribución",
                },
            ]

            if campaign.status in _TERMINAL_CAMPAIGN_STATUSES:
                next_action = {"code": "COMPLETE", "label": "Campaña cerrada", "view": "campaigns"}
                priority = 90
                requires_action = False
            elif not campaign.channels:
                next_action = {"code": "DEFINE_CHANNELS", "label": "Definir canales", "view": "campaigns"}
                priority = 0
                requires_action = True
            elif failed_publications:
                next_action = {"code": "FIX_PUBLICATION", "label": "Revisar publicación fallida", "view": "calendar"}
                priority = 0
                requires_action = True
            elif not linked_creatives:
                next_action = {"code": "CREATE_CREATIVE", "label": "Crear o vincular creativo", "view": "content"}
                priority = 1
                requires_action = True
            elif not ready_creatives:
                next_action = {"code": "FINISH_CREATIVE", "label": "Terminar creativo", "view": "content", "media_id": linked_creatives[0]["media"]["id"]}
                priority = 1
                requires_action = True
            elif organic_selected and not publications and not linked_paid:
                next_action = {"code": "PREPARE_DISTRIBUTION", "label": "Preparar distribución", "view": "content", "media_id": next((row["media"]["id"] for row in linked_creatives if row["effective_stage"] in _READY_CREATIVE_STAGES), None)}
                priority = 2
                requires_action = True
            elif queued_publications:
                next_action = {"code": "CALENDAR", "label": "Revisar calendario", "view": "calendar"}
                priority = 3
                requires_action = False
            elif draft_publications:
                next_action = {"code": "SCHEDULE_OR_PUBLISH", "label": "Programar publicación", "view": "calendar"}
                priority = 3
                requires_action = True
            elif paid_drafts:
                next_action = {"code": "REVIEW_PAID", "label": "Revisar pauta en borrador", "view": "pauta"}
                priority = 3
                requires_action = True
            elif planned_only_channels and not organic_selected and not linked_paid:
                next_action = {"code": "PLANNED_ONLY", "label": "Canal aún planificado", "view": "campaigns"}
                priority = 4
                requires_action = False
            elif published_publications or paid_remote_paused:
                next_action = {"code": "REVIEW_RESULTS", "label": "Revisar resultados", "view": "analytics"}
                priority = 4
                requires_action = False
            else:
                next_action = {"code": "COORDINATE", "label": "Coordinar distribución", "view": "content"}
                priority = 4
                requires_action = False

            cards.append({
                "campaign": {
                    "id": campaign.id,
                    "name": campaign.name,
                    "objective": campaign.objective,
                    "status": campaign.status,
                    "channels": list(campaign.channels),
                    "start_at": campaign.start_at,
                    "end_at": campaign.end_at,
                    "audience_contacts": len(campaign.audience_contact_ids),
                },
                "creative": {
                    "total": len(linked_creatives),
                    "ready": ready_creatives,
                    "counts": creative_counts,
                    "items": [
                        {
                            "media_id": row["media"]["id"],
                            "name": (row.get("creative") or {}).get("title") or row["media"].get("original_name"),
                            "kind": row["media"].get("kind"),
                            "stage": row.get("effective_stage"),
                        }
                        for row in linked_creatives
                    ],
                },
                "organic": {
                    "selected": organic_selected,
                    "counts": publication_counts,
                    "publications": len(publications),
                    "failed": failed_publications,
                },
                "paid": {
                    "plans": len(linked_paid),
                    "counts": paid_counts,
                    "remote_paused": paid_remote_paused,
                },
                "planned_only_channels": planned_only_channels,
                "steps": steps,
                "next_action": next_action,
                "priority": priority,
                "requires_action": requires_action,
            })

        cards.sort(key=lambda row: (row["priority"], row["campaign"].get("start_at") or "9999", row["campaign"]["name"].lower(), row["campaign"]["id"]))
        active = [row for row in cards if row["campaign"]["status"] not in _TERMINAL_CAMPAIGN_STATUSES]
        return {
            "schema": "binario.marketing.execution-workspace.v1",
            "company": {"id": company.id, "name": company.name},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "campaigns": len(cards),
                "active_campaigns": len(active),
                "requires_action": sum(1 for row in active if row["requires_action"]),
                "ready_creatives": sum(row["creative"]["ready"] for row in active),
                "queued_publications": sum(row["organic"]["counts"].get("QUEUED", 0) for row in active),
                "published_publications": sum(row["organic"]["counts"].get("PUBLISHED", 0) for row in active),
                "paid_remote_paused": sum(row["paid"]["remote_paused"] for row in active),
            },
            "campaigns": cards,
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "automatic_publish": False,
                "automatic_paid_activation": False,
                "automatic_campaign_mutation": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 64 adds only a local GET projection and browser execution surface."""

    def _wave64_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/commercial-pipeline.js":
            target = self.server.runtime.repo_root / "web" / "commercial-pipeline.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave64AfterCommercialPipeline(){
  if(document.querySelector('script[data-execution-workspace-wave64]'))return;
  const execution=document.createElement('script');
  execution.src='/execution-workspace.js';
  execution.defer=true;
  execution.dataset.executionWorkspaceWave64='1';
  document.head.append(execution);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/execution-workspace.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "execution-workspace":
                self._json(self.server.runtime.campaign_execution_workspace(parts[2]))
                return
        except Exception as exc:
            self._wave64_error(exc)
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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
