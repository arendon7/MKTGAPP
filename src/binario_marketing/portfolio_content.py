from __future__ import annotations

from datetime import datetime, timezone


PORTFOLIO_CONTENT_SCHEMA = "binario.marketing.portfolio-content.v1"
MAX_PORTFOLIO_CONTENT_ITEMS = 300
_STAGE_ORDER = {
    "UNPROFILED": 0,
    "BRIEF": 1,
    "DRAFT": 2,
    "READY": 3,
    "SCHEDULED": 4,
    "PUBLISHED": 5,
    "PAID": 6,
    "ARCHIVED": 7,
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _value(source: object, name: str, default=None):
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _company(source: object) -> dict:
    return {
        "id": _text(_value(source, "id")),
        "name": _text(_value(source, "name")) or "Empresa",
    }


def _project_item(company: dict, source: dict) -> dict | None:
    media = source.get("media") or {}
    media_id = _text(media.get("id"))
    if not media_id:
        return None
    creative = source.get("creative") or {}
    campaign = source.get("campaign") or None
    stage = _text(source.get("effective_stage") or creative.get("stage") or "UNPROFILED").upper()
    if stage not in _STAGE_ORDER:
        stage = "UNPROFILED"
    publications = source.get("publications") or []
    paid_media = source.get("paid_media") or []
    scheduled_for = next(
        (
            row.get("scheduled_for")
            for row in publications
            if _text(row.get("status")).upper() == "QUEUED" and row.get("scheduled_for")
        ),
        creative.get("publish_at"),
    )
    return {
        "company": dict(company),
        "media": {
            "id": media_id,
            "name": _text(media.get("original_name")) or _text(creative.get("title")) or "Contenido",
            "kind": _text(media.get("kind")).lower() or "unknown",
        },
        "title": _text(creative.get("title")) or _text(media.get("original_name")) or "Contenido",
        "stage": stage,
        "purpose": _text(creative.get("purpose")).upper() or None,
        "channels": [str(value) for value in (creative.get("channels") or []) if _text(value)],
        "campaign": {
            "id": _text(campaign.get("id")),
            "name": _text(campaign.get("name")) or "Campaña",
            "status": _text(campaign.get("status")).upper() or None,
        } if isinstance(campaign, dict) and _text(campaign.get("id")) else None,
        "scheduled_for": scheduled_for,
        "publication_count": len(publications),
        "paid_media_count": len(paid_media),
        "action": {
            "label": "Abrir contenido",
            "view": "content",
            "media_id": media_id,
        },
    }


def build_portfolio_content(
    companies: list[object],
    creative_contexts: dict[str, dict],
    *,
    generated_at: str | None = None,
) -> dict:
    """Aggregate canonical Creative Studio projections without creating a second content workflow."""
    company_records = sorted((_company(row) for row in companies), key=lambda row: (row["name"].casefold(), row["id"]))
    items: list[dict] = []
    company_summaries: list[dict] = []
    totals = {stage: 0 for stage in _STAGE_ORDER}
    local_errors = 0

    for company in company_records:
        context = creative_contexts.get(company["id"]) or {}
        local_error = bool(context.get("_local_state_error"))
        if local_error:
            local_errors += 1
        company_items: list[dict] = []
        counts = {stage: 0 for stage in _STAGE_ORDER}
        for source in context.get("items") or []:
            projected = _project_item(company, source)
            if projected is None:
                continue
            company_items.append(projected)
            counts[projected["stage"]] += 1
            totals[projected["stage"]] += 1
        items.extend(company_items)
        company_summaries.append({
            "company": dict(company),
            "state": "LOCAL_STATE_ERROR" if local_error else "CONTENT",
            "total_assets": len(company_items),
            "counts": counts,
            "social_ready": bool((context.get("meta") or {}).get("social_ready")),
            "ads_ready": bool((context.get("meta") or {}).get("ads_ready")),
        })

    items.sort(key=lambda row: (
        _STAGE_ORDER.get(row["stage"], 99),
        row["company"]["name"].casefold(),
        row["title"].casefold(),
        row["media"]["id"],
    ))
    total_items = len(items)
    displayed = items[:MAX_PORTFOLIO_CONTENT_ITEMS]

    return {
        "schema": PORTFOLIO_CONTENT_SCHEMA,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "summary": {
            "active_companies": len(company_records),
            "local_state_errors": local_errors,
            "total_assets": total_items,
            "unprofiled": totals["UNPROFILED"],
            "in_creation": totals["BRIEF"] + totals["DRAFT"],
            "ready": totals["READY"],
            "scheduled": totals["SCHEDULED"],
            "published": totals["PUBLISHED"],
            "paid": totals["PAID"],
            "archived": totals["ARCHIVED"],
        },
        "companies": company_summaries,
        "items": displayed,
        "scope": {
            "total": total_items,
            "displayed": len(displayed),
            "truncated": total_items > len(displayed),
            "cap": MAX_PORTFOLIO_CONTENT_ITEMS,
        },
        "contracts": {
            "creative_studio_is_content_state_authority": True,
            "company_media_is_asset_authority": True,
            "social_publications_are_distribution_authority": True,
            "existing_calendar_remains_schedule_authority": True,
            "owner_module_retains_mutation_authority": True,
            "no_duplicate_scheduler": True,
            "no_duplicate_publish_path": True,
            "queue_scope_declared": True,
        },
        "safety": {
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "content_mutation_performed": False,
            "publication_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }


__all__ = ["MAX_PORTFOLIO_CONTENT_ITEMS", "PORTFOLIO_CONTENT_SCHEMA", "build_portfolio_content"]
