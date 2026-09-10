from __future__ import annotations

from datetime import datetime, timezone


PORTFOLIO_CAMPAIGNS_SCHEMA = "binario.marketing.portfolio-campaigns.v1"
MAX_PORTFOLIO_CAMPAIGNS = 300
MAX_PORTFOLIO_PAID_PLANS = 300
_TERMINAL = {"COMPLETED", "ARCHIVED"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _value(source: object, name: str, default=None):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _company(source: object) -> dict:
    return {"id": _text(_value(source, "id")), "name": _text(_value(source, "name")) or "Empresa"}


def _safe_next_action(source: dict) -> dict:
    action = source.get("next_action") or {}
    return {
        "code": _text(action.get("code")).upper() or None,
        "label": _text(action.get("label")) or "Abrir campaña",
        "view": _text(action.get("view")) or "campaigns",
        "media_id": _text(action.get("media_id")) or None,
    }


def _campaign_row(company: dict, source: dict) -> dict | None:
    campaign = source.get("campaign") or {}
    campaign_id = _text(campaign.get("id"))
    if not campaign_id:
        return None
    execution = source.get("execution") or {}
    creative = execution.get("creative") or {}
    organic = execution.get("organic") or {}
    paid = execution.get("paid") or {}
    evidence = source.get("evidence") or {}
    attribution = source.get("attribution") or {}
    status = _text(campaign.get("status")).upper() or "PLANNING"
    return {
        "company": dict(company),
        "campaign": {
            "id": campaign_id,
            "name": _text(campaign.get("name")) or "Campaña",
            "objective": _text(campaign.get("objective")).upper() or None,
            "status": status,
            "channels": [str(value) for value in (campaign.get("channels") or []) if _text(value)],
            "start_at": campaign.get("start_at"),
            "end_at": campaign.get("end_at"),
        },
        "active": status not in _TERMINAL,
        "requires_attention": bool(source.get("requires_attention")),
        "execution": {
            "requires_action": bool(execution.get("requires_action")),
            "creative_ready": int(creative.get("ready") or 0),
            "creative_total": int(creative.get("total") or 0),
            "organic_publications": int(organic.get("publications") or 0),
            "organic_failed": int(organic.get("failed") or 0),
            "paid_plans": int(paid.get("plans") or 0),
            "paid_remote_paused": int(paid.get("remote_paused") or 0),
        },
        "evidence": {
            "level": _text(evidence.get("level")).upper() or "INSUFFICIENT",
            "label": _text(evidence.get("label")) or "Evidencia insuficiente",
            "has_signal": bool(evidence.get("has_signal")),
        },
        "attribution": {
            "opportunities": int(attribution.get("attributed_opportunities") or 0),
            "won": int(attribution.get("attributed_won") or 0),
        },
        "human_decision_recorded": source.get("decision") is not None,
        "ai_analysis_available": source.get("latest_ai") is not None,
        "next_action": _safe_next_action(source),
        "action": {"label": "Abrir campaña", "view": "campaigns", "campaign_id": campaign_id},
    }


def _paid_row(company: dict, source: dict) -> dict | None:
    draft_id = _text(source.get("id"))
    if not draft_id:
        return None
    plan = source.get("plan") or {}
    marketing_campaign = source.get("marketing_campaign") or {}
    linked_campaign_id = _text(marketing_campaign.get("id") or plan.get("campaign_id")) or None
    status = _text(source.get("status")).upper() or "DRAFT"
    return {
        "company": dict(company),
        "id": draft_id,
        "status": status,
        "campaign_name": _text(source.get("campaign_name")) or "Plan de pauta",
        "marketing_campaign": {
            "id": linked_campaign_id,
            "name": _text(marketing_campaign.get("name")) or None,
            "status": _text(marketing_campaign.get("status")).upper() or None,
        } if linked_campaign_id else None,
        "currency": _text(plan.get("currency")) or None,
        "start_at": plan.get("start_at"),
        "end_at": plan.get("end_at"),
        "remote_paused": status == "REMOTE_PAUSED",
        "action": {"label": "Abrir pauta", "view": "pauta", "paid_media_id": draft_id},
    }


def build_portfolio_campaigns(
    companies: list[object],
    intelligence_by_company: dict[str, dict],
    paid_media_by_company: dict[str, list[dict]],
    *,
    generated_at: str | None = None,
) -> dict:
    company_records = sorted((_company(row) for row in companies), key=lambda row: (row["name"].casefold(), row["id"]))
    campaigns: list[dict] = []
    paid_plans: list[dict] = []
    companies_summary: list[dict] = []
    local_errors = 0

    for company in company_records:
        intelligence = intelligence_by_company.get(company["id"]) or {}
        paid_source = paid_media_by_company.get(company["id"]) or []
        error = bool(intelligence.get("_local_state_error")) or bool(
            isinstance(paid_source, dict) and paid_source.get("_local_state_error")
        )
        if error:
            local_errors += 1
        local_campaigns = []
        for source in intelligence.get("campaigns") or []:
            row = _campaign_row(company, source)
            if row is not None:
                campaigns.append(row)
                local_campaigns.append(row)
        local_paid = []
        if isinstance(paid_source, list):
            for source in paid_source:
                row = _paid_row(company, source)
                if row is not None:
                    paid_plans.append(row)
                    local_paid.append(row)
        companies_summary.append({
            "company": dict(company),
            "state": "LOCAL_STATE_ERROR" if error else "CAMPAIGNS",
            "campaigns": len(local_campaigns),
            "active_campaigns": sum(1 for row in local_campaigns if row["active"]),
            "requires_attention": sum(1 for row in local_campaigns if row["active"] and row["requires_attention"]),
            "paid_plans": len(local_paid),
            "paid_drafts": sum(1 for row in local_paid if row["status"] == "DRAFT"),
            "paid_remote_paused": sum(1 for row in local_paid if row["status"] == "REMOTE_PAUSED"),
        })

    campaigns.sort(key=lambda row: (
        0 if row["active"] and row["requires_attention"] else 1 if row["active"] else 2,
        row["campaign"]["start_at"] or "9999",
        row["company"]["name"].casefold(),
        row["campaign"]["name"].casefold(),
        row["campaign"]["id"],
    ))
    paid_plans.sort(key=lambda row: (
        0 if row["status"] == "DRAFT" else 1 if row["status"] == "REMOTE_PAUSED" else 2,
        row["company"]["name"].casefold(),
        row["campaign_name"].casefold(),
        row["id"],
    ))
    campaign_total = len(campaigns)
    paid_total = len(paid_plans)
    visible_campaigns = campaigns[:MAX_PORTFOLIO_CAMPAIGNS]
    visible_paid = paid_plans[:MAX_PORTFOLIO_PAID_PLANS]
    active = [row for row in campaigns if row["active"]]

    return {
        "schema": PORTFOLIO_CAMPAIGNS_SCHEMA,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_companies": len(company_records),
            "local_state_errors": local_errors,
            "campaigns": campaign_total,
            "active_campaigns": len(active),
            "requires_attention": sum(1 for row in active if row["requires_attention"]),
            "execution_actions": sum(1 for row in active if row["execution"]["requires_action"]),
            "with_results_signal": sum(1 for row in active if row["evidence"]["has_signal"]),
            "attributed_opportunities": sum(row["attribution"]["opportunities"] for row in active),
            "attributed_won": sum(row["attribution"]["won"] for row in active),
            "paid_plans": paid_total,
            "paid_drafts": sum(1 for row in paid_plans if row["status"] == "DRAFT"),
            "paid_remote_paused": sum(1 for row in paid_plans if row["status"] == "REMOTE_PAUSED"),
        },
        "companies": companies_summary,
        "campaigns": visible_campaigns,
        "paid_media": visible_paid,
        "scope": {
            "campaigns_total": campaign_total,
            "campaigns_displayed": len(visible_campaigns),
            "campaigns_truncated": campaign_total > len(visible_campaigns),
            "paid_total": paid_total,
            "paid_displayed": len(visible_paid),
            "paid_truncated": paid_total > len(visible_paid),
        },
        "contracts": {
            "w65_is_campaign_intelligence_authority": True,
            "w64_is_execution_authority": True,
            "wave48_is_paid_media_mutation_authority": True,
            "owner_module_retains_mutation_authority": True,
            "no_duplicate_campaign_state": True,
            "no_duplicate_paid_execution_path": True,
            "no_cross_company_provider_reads": True,
            "queue_scope_declared": True,
        },
        "safety": {
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "campaign_mutation_performed": False,
            "paid_media_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }


__all__ = [
    "MAX_PORTFOLIO_CAMPAIGNS",
    "MAX_PORTFOLIO_PAID_PLANS",
    "PORTFOLIO_CAMPAIGNS_SCHEMA",
    "build_portfolio_campaigns",
]
