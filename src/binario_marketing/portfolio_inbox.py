from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Iterable

from .portfolio_inbox_refresh import company_has_inbox_mapping


SCHEMA = "binario.marketing.portfolio-inbox.v1"
MAX_PORTFOLIO_INBOX_ITEMS = 100
_URGENCY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _parse_timestamp(value: object) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _queue_key(row: dict) -> tuple:
    rank = row.get("rank")
    rank_value = rank if isinstance(rank, int) and not isinstance(rank, bool) else 999
    occurred = _parse_timestamp(row.get("occurred_at"))
    occurred_key = -(occurred.timestamp()) if occurred is not None else float("inf")
    return (
        rank_value,
        _URGENCY_ORDER.get(str(row.get("urgency") or "").upper(), 9),
        0 if row.get("blocking") else 1,
        occurred_key,
        str((row.get("company") or {}).get("name") or "").casefold(),
        str(row.get("portfolio_id") or ""),
    )


def _company_identity(company: object) -> dict:
    return {
        "id": str(getattr(company, "id", "") or ""),
        "name": str(getattr(company, "name", "") or ""),
    }


def build_portfolio_inbox(companies: Iterable[object], attention_by_company: dict[str, dict]) -> dict:
    """Aggregate minimized local Inbox attention without any provider read or mutation."""
    company_rows: list[dict] = []
    queue: list[dict] = []
    state_counts: dict[str, int] = {}

    active = sorted(
        [company for company in companies if bool(getattr(company, "active", True))],
        key=lambda company: (str(getattr(company, "name", "")).casefold(), str(getattr(company, "id", ""))),
    )
    configured = [company for company in active if company_has_inbox_mapping(company)]

    for company in configured:
        identity = _company_identity(company)
        attention = attention_by_company.get(identity["id"]) or {
            "snapshot_state": "LOCAL_STATE_ERROR",
            "captured_at": None,
            "items": [],
            "refresh_required": True,
            "provider_read_performed": False,
        }
        state = str(attention.get("snapshot_state") or "UNKNOWN").upper()
        state_counts[state] = state_counts.get(state, 0) + 1
        company_items: list[dict] = []
        for item in attention.get("items") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "").strip()
            interaction_id = str(item.get("interaction_id") or "").strip()
            if kind not in {"facebook_message", "instagram_comment"} or not interaction_id:
                continue
            row = deepcopy(item)
            row["portfolio_id"] = f"{identity['id']}:{kind}:{interaction_id}"
            row["company"] = deepcopy(identity)
            row["action"] = {
                "label": "Abrir en Inbox",
                "view": "inbox",
                "tab": kind,
                "entity_id": interaction_id,
            }
            company_items.append(row)
            queue.append(row)

        company_items.sort(key=_queue_key)
        company_rows.append({
            "company": identity,
            "snapshot_state": state,
            "captured_at": attention.get("captured_at"),
            "refresh_required": bool(attention.get("refresh_required")),
            "attention_count": len(company_items),
            "blocking": sum(1 for row in company_items if bool(row.get("blocking"))),
            "items": company_items[:20],
        })

    queue.sort(key=_queue_key)
    queue = queue[:MAX_PORTFOLIO_INBOX_ITEMS]
    summary = {
        "active_companies": len(active),
        "configured_companies": len(configured),
        "companies_with_attention": sum(1 for row in company_rows if row["attention_count"]),
        "companies_requiring_refresh": sum(1 for row in company_rows if row["refresh_required"]),
        "attention_total": len(queue),
        "blocking": sum(1 for row in queue if bool(row.get("blocking"))),
        "high": sum(1 for row in queue if str(row.get("urgency") or "").upper() == "HIGH"),
        "medium": sum(1 for row in queue if str(row.get("urgency") or "").upper() == "MEDIUM"),
        "low": sum(1 for row in queue if str(row.get("urgency") or "").upper() == "LOW"),
        "facebook_messages": sum(1 for row in queue if row.get("kind") == "facebook_message"),
        "instagram_comments": sum(1 for row in queue if row.get("kind") == "instagram_comment"),
        "reply_verifications": sum(1 for row in queue if row.get("attention_kind") == "reply_verification"),
        "snapshot_states": state_counts,
    }

    return {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "next_attention": queue[0] if queue else None,
        "companies": company_rows,
        "queue": queue,
        "contracts": {
            "source": "MINIMIZED_LOCAL_INBOX_ATTENTION",
            "existing_inbox_attention_is_resolution_authority": True,
            "existing_attention_rank_is_priority_authority": True,
            "cross_company_order_is_deterministic": True,
            "max_items": MAX_PORTFOLIO_INBOX_ITEMS,
            "provider_person_ids_excluded": True,
            "provider_links_excluded": True,
            "full_provider_bodies_excluded": True,
            "human_owner_handoff_required": True,
        },
        "safety": {
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "crm_mutation_performed": False,
            "reply_performed": False,
            "publishing_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }


__all__ = ["SCHEMA", "MAX_PORTFOLIO_INBOX_ITEMS", "build_portfolio_inbox"]
