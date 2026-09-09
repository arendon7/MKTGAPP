from __future__ import annotations

from datetime import datetime, timezone


PORTFOLIO_CRM_SCHEMA = "binario.marketing.portfolio-crm.v1"
MAX_PORTFOLIO_CRM_OPPORTUNITIES = 200
MAX_PORTFOLIO_CRM_ACTIVITIES = 200
_CLOSED_STAGES = {"WON", "LOST"}
_ACTIVITY_KINDS = {"crm_overdue", "crm_today", "crm_unscheduled"}
_OVERDUE_OPPORTUNITY_CODES = {"OVERDUE_FOLLOWUP", "OVERDUE_NEXT_ACTION"}
_UNSCHEDULED_OPPORTUNITY_CODES = {"NO_FOLLOWUP", "UNSCHEDULED_NEXT_ACTION", "UNSCHEDULED_FOLLOWUP"}


def _value(source: object, name: str, default=None):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _text(value: object) -> str:
    return str(value or "").strip()


def _company(company: object) -> dict:
    return {"id": _text(_value(company, "id")), "name": _text(_value(company, "name")) or "Empresa"}


def _due_key(value: object) -> tuple[bool, str]:
    text = _text(value)
    return (not bool(text), text)


def _opportunity_row(company: dict, row: dict) -> dict | None:
    opportunity_id = _text(row.get("id"))
    stage = _text(row.get("stage")).upper()
    attention = row.get("attention") or {}
    if not opportunity_id or stage in _CLOSED_STAGES or not bool(attention.get("requires_attention")):
        return None
    code = _text(attention.get("code")).upper()
    if not code or code == "CLOSED":
        return None
    followup = row.get("followup") or {}
    return {
        "company": dict(company),
        "id": opportunity_id,
        "title": _text(row.get("title")) or "Oportunidad",
        "stage": stage,
        "value": row.get("value"),
        "currency": _text(row.get("currency")).upper() or None,
        "next_action_at": row.get("next_action_at"),
        "followup": {
            "pending_activities": int(followup.get("pending_activities") or 0),
            "overdue_activities": int(followup.get("overdue_activities") or 0),
            "next_due_at": followup.get("next_due_at"),
            "next_activity_id": _text(followup.get("next_activity_id")) or None,
        },
        "attention": {
            "code": code,
            "label": _text(attention.get("label")) or "Revisar oportunidad",
            "priority": int(attention.get("priority") if isinstance(attention.get("priority"), int) else 99),
        },
        "action": {
            "label": "Abrir oportunidad",
            "view": "crm",
            "tab": "pipeline",
            "opportunity_id": opportunity_id,
        },
    }


def _activity_row(company: dict, row: dict, opportunity_titles: dict[str, str]) -> dict | None:
    kind = _text(row.get("kind")).lower()
    activity_id = _text(row.get("entity_id"))
    if kind not in _ACTIVITY_KINDS or not activity_id:
        return None
    opportunity_id = _text(row.get("opportunity_id")) or None
    labels = {
        "crm_overdue": "Seguimiento vencido",
        "crm_today": "Seguimiento de hoy",
        "crm_unscheduled": "Seguimiento sin fecha",
    }
    return {
        "company": dict(company),
        "id": activity_id,
        "kind": kind,
        "label": labels[kind],
        "due_at": row.get("due_at"),
        "opportunity_id": opportunity_id,
        "opportunity_title": opportunity_titles.get(opportunity_id or ""),
        "owner_priority": int(row.get("priority") if isinstance(row.get("priority"), int) else 99),
        "action": {
            "label": "Abrir seguimiento",
            "view": "crm",
            "tab": "followups",
            "entity_id": activity_id,
            "opportunity_id": opportunity_id,
        },
    }


def build_portfolio_crm(
    companies: list[object],
    pipelines: dict[str, dict],
    workdesks: dict[str, dict],
    *,
    generated_at: str | None = None,
) -> dict:
    """Aggregate existing local CRM projections without inventing cross-type priority."""
    company_records = sorted((_company(company) for company in companies), key=lambda row: (row["name"].casefold(), row["id"]))
    opportunities: list[dict] = []
    activities: list[dict] = []
    company_summaries: list[dict] = []
    local_errors = 0
    total_open_opportunities = 0
    total_pending_activities = 0

    for company in company_records:
        company_id = company["id"]
        pipeline = pipelines.get(company_id) or {}
        workdesk = workdesks.get(company_id) or {}
        pipeline_error = bool(pipeline.get("_local_state_error"))
        workdesk_error = bool(workdesk.get("_local_state_error"))
        if pipeline_error or workdesk_error:
            local_errors += 1

        opportunity_titles: dict[str, str] = {}
        company_opportunities: list[dict] = []
        for lane in pipeline.get("lanes") or []:
            for source_row in lane.get("opportunities") or []:
                source_id = _text(source_row.get("id"))
                if source_id:
                    opportunity_titles[source_id] = _text(source_row.get("title")) or "Oportunidad"
                projected = _opportunity_row(company, source_row)
                if projected is not None:
                    company_opportunities.append(projected)

        company_activities: list[dict] = []
        for source_row in workdesk.get("queue") or []:
            projected = _activity_row(company, source_row, opportunity_titles)
            if projected is not None:
                company_activities.append(projected)

        opportunities.extend(company_opportunities)
        activities.extend(company_activities)
        pipeline_summary = pipeline.get("summary") or {}
        crm_summary = workdesk.get("crm") or {}
        total_open_opportunities += int(pipeline_summary.get("open_opportunities") or 0)
        total_pending_activities += int(crm_summary.get("pending") or 0)
        company_summaries.append({
            "company": dict(company),
            "state": "LOCAL_STATE_ERROR" if pipeline_error or workdesk_error else ("ATTENTION" if company_opportunities or company_activities else "CLEAR"),
            "opportunity_attention": len(company_opportunities),
            "activity_attention": len(company_activities),
            "open_opportunities": int(pipeline_summary.get("open_opportunities") or 0),
            "pending_activities": int(crm_summary.get("pending") or 0),
        })

    opportunities.sort(key=lambda row: (
        int((row.get("attention") or {}).get("priority") or 0),
        *_due_key((row.get("followup") or {}).get("next_due_at") or row.get("next_action_at")),
        row["company"]["name"].casefold(),
        row["id"],
    ))
    activities.sort(key=lambda row: (
        int(row.get("owner_priority") or 0),
        *_due_key(row.get("due_at")),
        row["company"]["name"].casefold(),
        row["id"],
    ))

    opportunity_total = len(opportunities)
    activity_total = len(activities)
    displayed_opportunities = opportunities[:MAX_PORTFOLIO_CRM_OPPORTUNITIES]
    displayed_activities = activities[:MAX_PORTFOLIO_CRM_ACTIVITIES]
    overdue_opportunities = sum(1 for row in opportunities if (row.get("attention") or {}).get("code") in _OVERDUE_OPPORTUNITY_CODES)
    unscheduled_opportunities = sum(1 for row in opportunities if (row.get("attention") or {}).get("code") in _UNSCHEDULED_OPPORTUNITY_CODES)
    overdue_activities = sum(1 for row in activities if row.get("kind") == "crm_overdue")
    today_activities = sum(1 for row in activities if row.get("kind") == "crm_today")
    unscheduled_activities = sum(1 for row in activities if row.get("kind") == "crm_unscheduled")

    return {
        "schema": PORTFOLIO_CRM_SCHEMA,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_companies": len(company_records),
            "companies_with_attention": sum(1 for row in company_summaries if row["state"] == "ATTENTION"),
            "local_state_errors": local_errors,
            "open_opportunities": total_open_opportunities,
            "pending_activities": total_pending_activities,
            "opportunity_attention": opportunity_total,
            "activity_attention": activity_total,
            "overdue_opportunities": overdue_opportunities,
            "unscheduled_opportunities": unscheduled_opportunities,
            "overdue_activities": overdue_activities,
            "today_activities": today_activities,
            "unscheduled_activities": unscheduled_activities,
        },
        "companies": company_summaries,
        "opportunities": displayed_opportunities,
        "activities": displayed_activities,
        "scope": {
            "opportunity_total": opportunity_total,
            "opportunity_displayed": len(displayed_opportunities),
            "opportunity_truncated": opportunity_total > len(displayed_opportunities),
            "activity_total": activity_total,
            "activity_displayed": len(displayed_activities),
            "activity_truncated": activity_total > len(displayed_activities),
            "opportunity_cap": MAX_PORTFOLIO_CRM_OPPORTUNITIES,
            "activity_cap": MAX_PORTFOLIO_CRM_ACTIVITIES,
        },
        "contracts": {
            "commercial_pipeline_is_opportunity_attention_authority": True,
            "daily_workdesk_is_activity_timing_authority": True,
            "opportunity_and_activity_queues_remain_separate": True,
            "no_cross_type_priority_score": True,
            "closed_opportunities_suppressed": True,
            "completed_activities_suppressed_by_owner_projection": True,
            "owner_module_retains_mutation_authority": True,
            "cross_company_contact_pii_omitted": True,
            "queue_scope_declared": True,
        },
        "safety": {
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "crm_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }


__all__ = [
    "MAX_PORTFOLIO_CRM_ACTIVITIES",
    "MAX_PORTFOLIO_CRM_OPPORTUNITIES",
    "PORTFOLIO_CRM_SCHEMA",
    "build_portfolio_crm",
]
