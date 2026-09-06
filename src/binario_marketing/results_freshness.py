from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone


RESULTS_FRESHNESS_SCHEMA = "binario.marketing.results-decision-freshness.v1"
ACTIVE_RESULTS_MAX_AGE_SECONDS = 24 * 60 * 60
_TERMINAL_CAMPAIGN_STATUSES = {"COMPLETED", "ARCHIVED"}
_EXECUTION_BLOCKERS = {"FIX_EXECUTION"}


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("freshness clock must be timezone-aware")
    return current.astimezone(timezone.utc)


def _timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def snapshot_decision_freshness(latest_snapshot: dict | None, *, now: datetime | None = None) -> dict:
    """Classify whether one company snapshot is recent enough for a new active-campaign decision.

    This is an operator cadence guard, not a performance or generic evidence-staleness judgment.
    Historical evidence remains valid as history even when a new refresh is required.
    """
    current = _utc(now)
    if not latest_snapshot:
        return {
            "schema": RESULTS_FRESHNESS_SCHEMA,
            "state": "MISSING",
            "created_at": None,
            "age_seconds": None,
            "max_age_seconds": ACTIVE_RESULTS_MAX_AGE_SECONDS,
            "decision_refresh_required": True,
            "reason": "No hay snapshot de resultados disponible.",
        }

    created_at = latest_snapshot.get("created_at")
    observed = _timestamp(created_at)
    if observed is None:
        return {
            "schema": RESULTS_FRESHNESS_SCHEMA,
            "state": "INVALID_TIMESTAMP",
            "created_at": created_at,
            "age_seconds": None,
            "max_age_seconds": ACTIVE_RESULTS_MAX_AGE_SECONDS,
            "decision_refresh_required": True,
            "reason": "La fecha del último snapshot no es verificable.",
        }

    age_seconds = (current - observed).total_seconds()
    if age_seconds < 0:
        return {
            "schema": RESULTS_FRESHNESS_SCHEMA,
            "state": "FUTURE_OBSERVATION",
            "created_at": created_at,
            "age_seconds": None,
            "max_age_seconds": ACTIVE_RESULTS_MAX_AGE_SECONDS,
            "decision_refresh_required": True,
            "reason": "El último snapshot tiene una fecha futura y no puede autorizar una decisión nueva.",
        }

    age = int(age_seconds)
    refresh_required = age > ACTIVE_RESULTS_MAX_AGE_SECONDS
    return {
        "schema": RESULTS_FRESHNESS_SCHEMA,
        "state": "REFRESH_DUE" if refresh_required else "CURRENT",
        "created_at": created_at,
        "age_seconds": age,
        "max_age_seconds": ACTIVE_RESULTS_MAX_AGE_SECONDS,
        "decision_refresh_required": refresh_required,
        "reason": (
            "La evidencia tiene más de 24 horas; actualízala antes de registrar una nueva decisión o pedir análisis IA."
            if refresh_required
            else "La evidencia está dentro de la ventana operativa de 24 horas para una decisión nueva."
        ),
    }


def campaign_has_distribution(row: dict) -> bool:
    execution = row.get("execution") or {}
    organic = execution.get("organic") or {}
    counts = organic.get("counts") or {}
    paid = execution.get("paid") or {}
    return bool(int(counts.get("PUBLISHED") or 0) or paid.get("remote_paused"))


def apply_results_decision_freshness(payload: dict, *, now: datetime | None = None) -> dict:
    """Add an explicit refresh-before-decision guard to Wave65 results without mutating source evidence."""
    if not isinstance(payload, dict):
        raise ValueError("results intelligence payload must be an object")
    result = deepcopy(payload)
    freshness = snapshot_decision_freshness(result.get("latest_snapshot"), now=now)
    refresh_due = 0
    applicable = 0

    for row in result.get("campaigns") or []:
        campaign = row.get("campaign") or {}
        active = str(campaign.get("status") or "").strip().upper() not in _TERMINAL_CAMPAIGN_STATUSES
        distributed = campaign_has_distribution(row)
        guard_applies = bool(active and distributed)
        row_freshness = dict(freshness)
        row_freshness["guard_applies"] = guard_applies
        row_freshness["active_campaign"] = active
        row_freshness["distribution_exists"] = distributed
        row_freshness["generic_business_staleness_judgment"] = False
        row_freshness["historical_evidence_preserved"] = True
        row_freshness["decision_refresh_required"] = bool(guard_applies and freshness["decision_refresh_required"])
        evidence = dict(row.get("evidence") or {})
        evidence["operational_freshness"] = row_freshness
        row["evidence"] = evidence

        if not guard_applies:
            continue
        applicable += 1
        if not row_freshness["decision_refresh_required"]:
            continue
        refresh_due += 1
        next_action = row.get("next_action") or {}
        if str(next_action.get("code") or "").strip().upper() in _EXECUTION_BLOCKERS:
            row_freshness["deferred_by_execution_blocker"] = True
            continue
        row_freshness["deferred_by_execution_blocker"] = False
        row["next_action"] = {
            "code": "CAPTURE_RESULTS",
            "label": "Actualizar resultados antes de decidir",
            "view": "analytics",
        }
        row["priority"] = min(int(row.get("priority") or 99), 1)
        row["requires_attention"] = True
        summary = str(evidence.get("summary") or "").strip()
        evidence["summary"] = (
            f"Actualización requerida por cadencia operativa: {row_freshness['reason']}"
            + (f" · Evidencia histórica: {summary}" if summary else "")
        )

    summary = dict(result.get("summary") or {})
    summary["decision_refresh_due"] = refresh_due
    summary["decision_freshness_applicable"] = applicable
    result["summary"] = summary
    result["freshness_policy"] = {
        "schema": RESULTS_FRESHNESS_SCHEMA,
        "active_distributed_campaigns_only": True,
        "max_age_seconds": ACTIVE_RESULTS_MAX_AGE_SECONDS,
        "max_age_hours": 24,
        "purpose": "REFRESH_BEFORE_NEW_DECISION_OR_CAMPAIGN_AI",
        "generic_business_staleness_judgment": False,
        "historical_evidence_preserved": True,
        "provider_refresh_automatic": False,
    }
    return result


def campaign_decision_refresh_required(payload: dict, campaign_id: str) -> tuple[bool, dict]:
    matches = [
        row for row in payload.get("campaigns") or []
        if (row.get("campaign") or {}).get("id") == campaign_id
    ]
    if len(matches) != 1:
        raise ValueError("campaign freshness context is not uniquely represented")
    freshness = ((matches[0].get("evidence") or {}).get("operational_freshness") or {})
    return bool(freshness.get("decision_refresh_required")), freshness


__all__ = [
    "ACTIVE_RESULTS_MAX_AGE_SECONDS",
    "RESULTS_FRESHNESS_SCHEMA",
    "apply_results_decision_freshness",
    "campaign_decision_refresh_required",
    "campaign_has_distribution",
    "snapshot_decision_freshness",
]
