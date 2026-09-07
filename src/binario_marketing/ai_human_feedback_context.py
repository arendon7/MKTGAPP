from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Iterable

from .ai_recommendation_review import current_recommendations
from .company_store import COMPANY_ID_RE


AI_HUMAN_FEEDBACK_CONTEXT_SCHEMA = "binario.marketing.ai-human-feedback-context.v1"
MAX_FEEDBACK_ITEMS = 12


def _company(value: object) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def _value(row: object, key: str, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _payload(row: object) -> dict:
    if isinstance(row, dict):
        return dict(row)
    if is_dataclass(row):
        return asdict(row)
    raise ValueError("unsupported feedback row")


def _target_key(*, task: object, campaign_id: object, creative_media_id: object) -> tuple[str, str, str]:
    return (
        str(task or "").strip().upper(),
        str(campaign_id or "").strip(),
        str(creative_media_id or "").strip(),
    )


def _session_target(session: object) -> tuple[str, str, str]:
    return _target_key(
        task=_value(session, "task"),
        campaign_id=_value(session, "campaign_id"),
        creative_media_id=_value(session, "creative_media_id"),
    )


def _session_order(session: object) -> tuple[str, str]:
    return (
        str(_value(session, "created_at") or ""),
        str(_value(session, "id") or ""),
    )


def project_ai_human_feedback_context(
    company_id: str,
    *,
    task: str,
    campaign_id: str | None,
    creative_media_id: str | None,
    sessions: Iterable[object],
    reviews: Iterable[object],
    resolutions: Iterable[object],
    evidence: dict | None,
) -> dict:
    """Project operator feedback for the exact AI target without turning it into truth or causality."""
    company = _company(company_id)
    target = _target_key(task=task, campaign_id=campaign_id, creative_media_id=creative_media_id)
    if target[0] not in {"STRATEGY", "CAMPAIGN", "CREATIVE"}:
        raise ValueError("unsupported AI feedback target task")

    review_by_id: dict[str, dict] = {}
    for row in reviews:
        payload = _payload(row)
        if payload.get("company_id") == company and payload.get("decision") in {"ACCEPTED", "DISMISSED"}:
            review_by_id[str(payload.get("recommendation_id") or "")] = payload

    resolution_by_id: dict[str, dict] = {}
    for row in resolutions:
        payload = _payload(row)
        if payload.get("company_id") == company and payload.get("outcome") in {"APPLIED", "NOT_APPLIED"}:
            resolution_by_id[str(payload.get("recommendation_id") or "")] = payload

    evidence_by_id = {
        str(row.get("recommendation_id") or ""): row
        for row in ((evidence or {}).get("recommendations") or [])
        if isinstance(row, dict)
    }

    session_rows = sorted(list(sessions), key=_session_order, reverse=True)
    items: list[dict] = []
    for session in session_rows:
        if _session_target(session) != target:
            continue
        for recommendation in current_recommendations([session]):
            recommendation_id = recommendation["recommendation_id"]
            review = review_by_id.get(recommendation_id)
            if review is None:
                # Only human-reviewed proposals are feedback. Unreviewed model output is intentionally omitted.
                continue
            if (
                review.get("session_id") != recommendation.get("session_id")
                or review.get("recommendation_sha256") != recommendation.get("recommendation_sha256")
            ):
                continue
            resolution = resolution_by_id.get(recommendation_id)
            if resolution is not None and (
                resolution.get("session_id") != recommendation.get("session_id")
                or resolution.get("recommendation_sha256") != recommendation.get("recommendation_sha256")
            ):
                resolution = None
            observed = evidence_by_id.get(recommendation_id) or {}
            evidence_state = str(observed.get("state") or "").strip().upper() or None
            items.append({
                "recommendation_id": recommendation_id,
                "session_id": recommendation.get("session_id"),
                "session_created_at": recommendation.get("session_created_at"),
                "historical_proposal": {
                    # Deliberately bounded prior model text: no rationale, no next_step and no full model output.
                    "title": str(recommendation.get("title") or "")[:220],
                    "area": recommendation.get("area"),
                    "suggested_priority": recommendation.get("priority"),
                    "is_prior_ai_output_not_verified_fact": True,
                },
                "human_review": {
                    "decision": review.get("decision"),
                    "decided_at": review.get("decided_at"),
                },
                "human_handoff": {
                    "outcome": resolution.get("outcome") if resolution else None,
                    "resolved_at": resolution.get("resolved_at") if resolution else None,
                    "applied_is_not_business_execution_proof": True,
                },
                "post_application_observation": {
                    "state": evidence_state,
                    "available": bool(evidence_state),
                    "is_observational_not_causal": True,
                    "causal_attribution_to_ai": False,
                },
            })
            if len(items) >= MAX_FEEDBACK_ITEMS:
                break
        if len(items) >= MAX_FEEDBACK_ITEMS:
            break

    counts = {
        "accepted": 0,
        "dismissed": 0,
        "applied": 0,
        "not_applied": 0,
        "with_observational_followup": 0,
    }
    for row in items:
        decision = (row.get("human_review") or {}).get("decision")
        outcome = (row.get("human_handoff") or {}).get("outcome")
        if decision == "ACCEPTED":
            counts["accepted"] += 1
        elif decision == "DISMISSED":
            counts["dismissed"] += 1
        if outcome == "APPLIED":
            counts["applied"] += 1
        elif outcome == "NOT_APPLIED":
            counts["not_applied"] += 1
        if (row.get("post_application_observation") or {}).get("available"):
            counts["with_observational_followup"] += 1

    return {
        "schema": AI_HUMAN_FEEDBACK_CONTEXT_SCHEMA,
        "company_id": company,
        "scope": {
            "task": target[0],
            "campaign_id": target[1] or None,
            "creative_media_id": target[2] or None,
            "exact_target_only": True,
        },
        "summary": {"items": len(items), **counts},
        "items": items,
        "interpretation_rules": [
            "Historical proposal text is prior AI output, not verified business truth.",
            "Human ACCEPTED/DISMISSED and APPLIED/NOT_APPLIED are operator continuity signals, not performance scores.",
            "APPLIED does not prove that a business/provider mutation occurred.",
            "Later evidence states are observational and do not prove that Astra or the recommendation caused an outcome.",
            "Avoid mechanically repeating DISMISSED or NOT_APPLIED proposals; revisit only when current supplied context materially justifies it and explain the new rationale.",
            "Do not automatically prefer or prioritize ACCEPTED/APPLIED proposals merely because the operator accepted them before.",
        ],
        "contracts": {
            "human_review_required_for_feedback_item": True,
            "exact_target_only": True,
            "prior_ai_text_is_untrusted_history": True,
            "full_prior_output_included": False,
            "prior_rationale_included": False,
            "prior_next_step_included": False,
            "causal_attribution_to_ai": False,
            "operator_feedback_is_not_performance_score": True,
            "automatic_generation": False,
            "history_order": "SESSION_CREATED_AT_DESC",
        },
        "privacy": {
            "contact_pii_included": False,
            "provider_secrets_included": False,
            "media_bytes_included": False,
        },
    }


__all__ = [
    "AI_HUMAN_FEEDBACK_CONTEXT_SCHEMA",
    "MAX_FEEDBACK_ITEMS",
    "project_ai_human_feedback_context",
]
