from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from urllib.parse import urlparse

from .crm_store import STAGES
from . import service_wave62_app as base


_STAGE_LABELS = {
    "NEW": "Nuevo",
    "CONTACTED": "Contactado",
    "INTERESTED": "Interesado",
    "PROPOSAL": "Propuesta",
    "WON": "Ganado",
    "LOST": "Perdido",
}
_CLOSED_STAGES = {"WON", "LOST"}


def _moment(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _amounts_by_currency(rows: list[dict]) -> list[dict]:
    buckets: dict[str, dict] = {}
    for row in rows:
        currency = str(row.get("currency") or "").strip().upper() or "UNK"
        bucket = buckets.setdefault(currency, {
            "currency": currency,
            "value": 0,
            "opportunities": 0,
            "valued_opportunities": 0,
        })
        bucket["opportunities"] += 1
        value = row.get("value")
        if value is not None:
            bucket["value"] += int(value)
            bucket["valued_opportunities"] += 1
    return [buckets[key] for key in sorted(buckets)]


class AppRuntime(base.AppRuntime):
    """Wave 63 projects the canonical CRM into a prioritized, local commercial pipeline."""

    def commercial_pipeline(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        contacts = {row.id: row for row in self.crm.list_contacts(company.id)}
        opportunities = [asdict(row) for row in self.crm.list_opportunities(company.id)]
        activities = [asdict(row) for row in self.crm.list_activities(company.id)]
        activities_by_opportunity: dict[str, list[dict]] = {}
        for activity in activities:
            opportunity_id = activity.get("opportunity_id")
            if opportunity_id:
                activities_by_opportunity.setdefault(opportunity_id, []).append(activity)

        now = datetime.now(timezone.utc)
        due_soon = now + timedelta(hours=48)
        lanes: dict[str, list[dict]] = {stage: [] for stage in STAGES}

        for opportunity in opportunities:
            stage = opportunity["stage"]
            contact = contacts.get(opportunity.get("contact_id"))
            related = activities_by_opportunity.get(opportunity["id"], [])
            pending = [row for row in related if not row.get("completed_at")]
            pending.sort(key=lambda row: (row.get("due_at") or "9999", row.get("created_at") or "", row["id"]))
            overdue = [row for row in pending if _moment(row.get("due_at")) is not None and _moment(row.get("due_at")) < now]

            due_candidates: list[tuple[datetime, str]] = []
            opportunity_due = _moment(opportunity.get("next_action_at"))
            if opportunity_due is not None:
                due_candidates.append((opportunity_due, opportunity.get("next_action_at") or ""))
            for activity in pending:
                activity_due = _moment(activity.get("due_at"))
                if activity_due is not None:
                    due_candidates.append((activity_due, activity.get("due_at") or ""))
            due_candidates.sort(key=lambda row: row[0])
            effective_due_at = due_candidates[0][1] if due_candidates else None
            effective_due = due_candidates[0][0] if due_candidates else None

            if stage in _CLOSED_STAGES:
                attention_code = "CLOSED"
                attention_label = "Cerrada"
                priority = 90
                requires_attention = False
            elif overdue:
                attention_code = "OVERDUE_FOLLOWUP"
                attention_label = "Seguimiento vencido"
                priority = 0
                requires_attention = True
            elif opportunity_due is not None and opportunity_due < now:
                attention_code = "OVERDUE_NEXT_ACTION"
                attention_label = "Próxima acción vencida"
                priority = 0
                requires_attention = True
            elif not pending and not opportunity.get("next_action") and not opportunity.get("next_action_at"):
                attention_code = "NO_FOLLOWUP"
                attention_label = "Sin siguiente acción"
                priority = 1
                requires_attention = True
            elif not pending and opportunity.get("next_action") and not opportunity.get("next_action_at"):
                attention_code = "UNSCHEDULED_NEXT_ACTION"
                attention_label = "Acción sin fecha"
                priority = 1
                requires_attention = True
            elif pending and effective_due is None:
                attention_code = "UNSCHEDULED_FOLLOWUP"
                attention_label = "Seguimiento sin fecha"
                priority = 1
                requires_attention = True
            elif effective_due is not None and effective_due <= due_soon:
                attention_code = "DUE_SOON"
                attention_label = "Vence pronto"
                priority = 2
                requires_attention = True
            elif stage == "PROPOSAL":
                attention_code = "PROPOSAL_ACTIVE"
                attention_label = "Propuesta activa"
                priority = 3
                requires_attention = False
            else:
                attention_code = "ON_TRACK"
                attention_label = "En curso"
                priority = 4
                requires_attention = False

            card = {
                "id": opportunity["id"],
                "title": opportunity["title"],
                "stage": stage,
                "value": opportunity.get("value"),
                "currency": opportunity.get("currency"),
                "next_action": opportunity.get("next_action"),
                "next_action_at": opportunity.get("next_action_at"),
                "notes": opportunity.get("notes"),
                "created_at": opportunity.get("created_at"),
                "updated_at": opportunity.get("updated_at"),
                "contact": None if contact is None else {
                    "id": contact.id,
                    "name": contact.name,
                    "organization": contact.organization,
                    "source": contact.source,
                },
                "followup": {
                    "pending_activities": len(pending),
                    "overdue_activities": len(overdue),
                    "next_due_at": effective_due_at,
                    "next_activity_id": pending[0]["id"] if pending else None,
                },
                "attention": {
                    "code": attention_code,
                    "label": attention_label,
                    "priority": priority,
                    "requires_attention": requires_attention,
                },
            }
            lanes[stage].append(card)

        for stage in STAGES:
            lanes[stage].sort(key=lambda row: (
                row["attention"]["priority"],
                row["followup"]["next_due_at"] or row.get("next_action_at") or "9999",
                row.get("updated_at") or "",
                row["id"],
            ))

        open_cards = [row for stage in STAGES if stage not in _CLOSED_STAGES for row in lanes[stage]]
        attention_cards = [row for row in open_cards if row["attention"]["requires_attention"]]
        lane_payload = []
        for stage in STAGES:
            rows = lanes[stage]
            lane_payload.append({
                "stage": stage,
                "label": _STAGE_LABELS[stage],
                "count": len(rows),
                "amounts_by_currency": _amounts_by_currency(rows),
                "opportunities": rows,
            })

        return {
            "schema": "binario.marketing.commercial-pipeline.v1",
            "company": {"id": company.id, "name": company.name},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "opportunities": len(opportunities),
                "open_opportunities": len(open_cards),
                "requires_attention": len(attention_cards),
                "proposals": len(lanes["PROPOSAL"]),
                "won": len(lanes["WON"]),
                "lost": len(lanes["LOST"]),
                "amounts_by_currency": _amounts_by_currency(open_cards),
            },
            "lanes": lane_payload,
            "priority_contract": [
                "OVERDUE_FOLLOWUP_OR_ACTION",
                "MISSING_OR_UNSCHEDULED_FOLLOWUP",
                "DUE_WITHIN_48_HOURS",
                "ACTIVE_PROPOSAL",
                "ON_TRACK",
                "CLOSED",
            ],
            "stage_update_contract": {
                "method": "PATCH",
                "path": "/api/companies/{company_id}/opportunities/{opportunity_id}",
                "field": "stage",
                "automatic_on_select_change": False,
                "explicit_save_required": True,
            },
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "automatic_stage_change": False,
                "automatic_message_send": False,
                "background_polling": False,
                "cloud_required": False,
                "mixed_currency_aggregation": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 63 adds a GET-only pipeline projection and bundled browser enhancement."""

    def _wave63_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/contact-360.js":
            target = self.server.runtime.repo_root / "web" / "contact-360.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave63AfterContact360(){
  if(document.querySelector('script[data-commercial-pipeline-wave63]'))return;
  const pipeline=document.createElement('script');
  pipeline.src='/commercial-pipeline.js';
  pipeline.defer=true;
  pipeline.dataset.commercialPipelineWave63='1';
  document.head.append(pipeline);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/commercial-pipeline.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "commercial-pipeline":
                self._json(self.server.runtime.commercial_pipeline(parts[2]))
                return
        except Exception as exc:
            self._wave63_error(exc)
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
