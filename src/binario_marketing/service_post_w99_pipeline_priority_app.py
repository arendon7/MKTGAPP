from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from . import service_post_w99_action_center_app as base


_PIPELINE_RANK = {
    "OVERDUE_FOLLOWUP": (18, "CRITICAL", True),
    "OVERDUE_NEXT_ACTION": (19, "HIGH", False),
    "NO_FOLLOWUP": (34, "HIGH", False),
    "UNSCHEDULED_NEXT_ACTION": (39, "MEDIUM", False),
    "UNSCHEDULED_FOLLOWUP": (39, "MEDIUM", False),
    "DUE_SOON": (43, "MEDIUM", False),
}


def enrich_action_center_with_pipeline(*, payload: dict, pipeline: dict, workdesk: dict, commercial: dict) -> dict:
    """Add deterministic pipeline attention without probabilistic sales scoring."""
    result = deepcopy(payload)
    queue = list(result.get("queue") or [])
    workdesk_opportunities = {
        str(row.get("opportunity_id") or "")
        for row in workdesk.get("queue") or []
        if str(row.get("kind") or "").startswith("crm_") and row.get("opportunity_id")
    }
    handoff_followups = {
        str(row.get("opportunity_id") or "")
        for row in commercial.get("handoffs") or []
        if row.get("handoff_state") == "NEEDS_FOLLOWUP" and row.get("opportunity_id")
    }
    added = 0
    for lane in pipeline.get("lanes") or []:
        for opportunity in lane.get("opportunities") or []:
            attention = opportunity.get("attention") or {}
            if not attention.get("requires_attention"):
                continue
            code = base._text(attention.get("code")).upper()
            if code not in _PIPELINE_RANK:
                continue
            opportunity_id = base._text(opportunity.get("id"))
            if opportunity_id in workdesk_opportunities and code in {"OVERDUE_FOLLOWUP", "UNSCHEDULED_FOLLOWUP", "DUE_SOON"}:
                continue
            if opportunity_id in handoff_followups and code == "NO_FOLLOWUP":
                continue
            rank, urgency, blocking = _PIPELINE_RANK[code]
            contact = opportunity.get("contact") or {}
            value = opportunity.get("value")
            currency = base._text(opportunity.get("currency"), "")
            value_copy = f" · {currency} {int(value):,}" if value is not None and currency else ""
            queue.append(base._item(
                rank=rank,
                urgency=urgency,
                source="COMMERCIAL",
                kind=f"pipeline_{code.lower()}",
                title=f"{base._text(attention.get('label'), 'Revisar oportunidad')} · {base._text(opportunity.get('title'), 'Oportunidad')}",
                detail=f"{base._text(contact.get('name'), 'Contacto')} · {base._text(opportunity.get('stage'), 'pipeline')}{value_copy}",
                action_label="Abrir pipeline",
                view="crm",
                tab="pipeline",
                contact_id=contact.get("id"),
                opportunity_id=opportunity.get("id"),
                due_at=(opportunity.get("followup") or {}).get("next_due_at") or opportunity.get("next_action_at"),
                blocking=blocking,
                reason_code=f"PIPELINE_{code}",
                reason="El pipeline detectó una condición determinística de seguimiento o fecha. No es una predicción de cierre ni un score probabilístico.",
            ))
            added += 1

    deduped = {}
    for row in queue:
        current = deduped.get(row["id"])
        if current is None or (row["rank"], base._URGENCY_ORDER.get(row["urgency"], 9)) < (current["rank"], base._URGENCY_ORDER.get(current["urgency"], 9)):
            deduped[row["id"]] = row
    queue = list(deduped.values())
    queue.sort(key=lambda row: (
        row["rank"], base._URGENCY_ORDER.get(row["urgency"], 9), row.get("due_at") is None,
        row.get("due_at") or "", row["id"],
    ))
    queue = queue[:50]
    by_source = {key: 0 for key in ("OPERATIONS", "COMMERCIAL", "CAMPAIGN", "SETUP")}
    by_urgency = {key: 0 for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    for row in queue:
        by_source[row["source"]] = by_source.get(row["source"], 0) + 1
        by_urgency[row["urgency"]] = by_urgency.get(row["urgency"], 0) + 1

    summary = dict(result.get("summary") or {})
    summary.update({
        "queue_total": len(queue),
        "blocking": sum(1 for row in queue if row.get("blocking")),
        "critical": by_urgency["CRITICAL"], "high": by_urgency["HIGH"],
        "medium": by_urgency["MEDIUM"], "low": by_urgency["LOW"],
        "by_source": by_source, "pipeline_attention": added,
    })
    result["summary"] = summary
    result["next_action"] = queue[0] if queue else None
    result["queue"] = queue
    result["focus"] = {
        "now": [row for row in queue if row["urgency"] in {"CRITICAL", "HIGH"}][:8],
        "next": [row for row in queue if row["urgency"] == "MEDIUM"][:8],
        "later": [row for row in queue if row["urgency"] == "LOW"][:8],
    }
    contracts = dict(result.get("contracts") or {})
    contracts.update({
        "pipeline_attention_is_deterministic": True,
        "no_forecast_inference": True,
        "no_probability_of_close_inference": True,
        "opportunity_value_not_used_as_priority_score": True,
    })
    result["contracts"] = contracts
    return result


class AppRuntime(base.AppRuntime):
    """Post-W99 Action Center with deterministic pipeline attention."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def action_center(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        workdesk = self.daily_workdesk(company.id)
        commercial = self.commercial_desk(company.id)
        payload = base.compose_action_center(
            company={"id": company.id, "name": company.name},
            workdesk=workdesk,
            commercial=commercial,
            execution=self.campaign_execution_workspace(company.id),
            results=self.results_intelligence_workspace(company.id),
            command=self.marketing_command_center(company.id),
        )
        return enrich_action_center_with_pipeline(
            payload=payload,
            pipeline=self.commercial_pipeline(company.id),
            workdesk=workdesk,
            commercial=commercial,
        )


MarketingHTTPServer = base.MarketingHTTPServer
MarketingHandler = base.MarketingHandler


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create(); server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]; url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App · post-W99 pipeline priority: {url}"); print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "enrich_action_center_with_pipeline", "serve"]
