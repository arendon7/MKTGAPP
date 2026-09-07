from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .company_store import COMPANY_ID_RE


PORTFOLIO_INBOX_REFRESH_PLAN_SCHEMA = "binario.marketing.portfolio-inbox-refresh-plan.v1"
PORTFOLIO_INBOX_REFRESH_RESULT_SCHEMA = "binario.marketing.portfolio-inbox-refresh-result.v1"
MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES = 50


def _company_id(value: object) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def normalize_company_ids(value: object) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("company_ids must be an array")
    if not value:
        raise ValueError("company_ids must not be empty")
    if len(value) > MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES:
        raise ValueError("too many companies in one Inbox refresh")
    result: list[str] = []
    seen: set[str] = set()
    for raw in value:
        company_id = _company_id(raw)
        if company_id in seen:
            raise ValueError("company_ids must not contain duplicates")
        seen.add(company_id)
        result.append(company_id)
    return result


def _company_value(company: object, name: str):
    if isinstance(company, dict):
        return company.get(name)
    return getattr(company, name, None)


def company_has_inbox_mapping(company: object) -> bool:
    return bool(
        str(_company_value(company, "facebook_page_id") or "").strip()
        or str(_company_value(company, "instagram_id") or "").strip()
    )


def build_refresh_plan(companies: Iterable[object], attention_by_company: dict[str, dict]) -> dict:
    rows: list[dict] = []
    unmapped = 0
    for company in companies:
        company_id = _company_id(_company_value(company, "id"))
        name = str(_company_value(company, "name") or company_id).strip()[:220] or company_id
        if not company_has_inbox_mapping(company):
            unmapped += 1
            continue
        attention = attention_by_company.get(company_id) or {}
        state = str(attention.get("snapshot_state") or "UNKNOWN").strip().upper()
        rows.append({
            "company_id": company_id,
            "company_name": name,
            "facebook_configured": bool(str(_company_value(company, "facebook_page_id") or "").strip()),
            "instagram_configured": bool(str(_company_value(company, "instagram_id") or "").strip()),
            "snapshot_state": state,
            "captured_at": attention.get("captured_at"),
            "refresh_required": bool(attention.get("refresh_required")),
            "attention_items": len(attention.get("items") or []),
            "provider_read_performed": False,
        })
    rows.sort(key=lambda row: (row["company_name"].casefold(), row["company_id"]))
    overflow = max(0, len(rows) - MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES)
    visible = rows[:MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES]
    return {
        "schema": PORTFOLIO_INBOX_REFRESH_PLAN_SCHEMA,
        "summary": {
            "configured_companies": len(rows),
            "unmapped_companies": unmapped,
            "refresh_required": sum(bool(row["refresh_required"]) for row in rows),
            "current": sum(row["snapshot_state"] == "CURRENT" for row in rows),
            "batch_limit": MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES,
            "eligible_overflow": overflow,
        },
        "companies": visible,
        "company_ids": [row["company_id"] for row in visible],
        "contracts": {
            "local_plan_only": True,
            "explicit_operator_post_required": True,
            "exact_company_ids_required": True,
            "configured_companies_only": True,
            "sequential_provider_reads": True,
            "per_company_failure_isolated": True,
            "automatic_retry": False,
            "raw_inbox_content_in_result": False,
        },
        "safety": {
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "crm_mutation_performed": False,
            "reply_performed": False,
            "ai_generation_performed": False,
            "automatic": False,
            "background_polling": False,
        },
    }


def aggregate_refresh_result(requested_ids: list[str], company_results: list[dict]) -> dict:
    requested = normalize_company_ids(requested_ids)
    by_id = {str(row.get("company_id") or ""): row for row in company_results if isinstance(row, dict)}
    rows: list[dict] = []
    for company_id in requested:
        source = by_id.get(company_id) or {}
        status = str(source.get("status") or "FAILED").strip().upper()
        if status not in {"REFRESHED", "FAILED"}:
            status = "FAILED"
        rows.append({
            "company_id": company_id,
            "company_name": str(source.get("company_name") or company_id)[:220],
            "status": status,
            "captured_at": source.get("captured_at") if status == "REFRESHED" else None,
            "attention_candidates": int(source.get("attention_candidates") or 0) if status == "REFRESHED" else 0,
            "provider_read_attempted": True,
            "raw_inbox_content_returned": False,
        })
    succeeded = sum(row["status"] == "REFRESHED" for row in rows)
    return {
        "schema": PORTFOLIO_INBOX_REFRESH_RESULT_SCHEMA,
        "summary": {
            "requested": len(requested),
            "refreshed": succeeded,
            "failed": len(requested) - succeeded,
        },
        "companies": rows,
        "contracts": {
            "requested_company_order_preserved": True,
            "per_company_failure_isolated": True,
            "raw_provider_errors_returned": False,
            "raw_inbox_content_returned": False,
            "automatic_retry": False,
        },
        "safety": {
            "provider_reads_were_operator_triggered": True,
            "provider_mutation_performed": False,
            "crm_mutation_performed": False,
            "reply_performed": False,
            "ai_generation_performed": False,
            "automatic": False,
            "background_polling": False,
        },
    }


__all__ = [
    "MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES",
    "PORTFOLIO_INBOX_REFRESH_PLAN_SCHEMA",
    "PORTFOLIO_INBOX_REFRESH_RESULT_SCHEMA",
    "aggregate_refresh_result",
    "build_refresh_plan",
    "company_has_inbox_mapping",
    "normalize_company_ids",
]
