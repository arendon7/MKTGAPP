from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from . import service_post_w99_action_center_app as action_base
from .ai_recommendation_handoff import RecommendationHandoffResolution, _route
from .ai_recommendation_review import current_recommendations
from .company_store import COMPANY_ID_RE


AI_RECOMMENDATION_EVIDENCE_SCHEMA = "binario.marketing.ai-recommendation-evidence-followup.v1"
FOLLOWUP_WINDOW_SECONDS = 24 * 60 * 60
MAX_TRACKED_RECOMMENDATIONS = 30


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
    raise ValueError("unsupported evidence row")


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


def _utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("evidence follow-up clock must be timezone-aware")
    return current.astimezone(timezone.utc)


def _historical_recommendations(sessions: Iterable[object]) -> dict[str, dict]:
    """Recover exact recommendations from every retained session using the canonical ID logic.

    Calling current_recommendations with one session at a time deliberately avoids the
    latest-per-target supersession rule while reusing the canonical parser and digest.
    """
    rows: dict[str, dict] = {}
    for session in sessions:
        for recommendation in current_recommendations([session]):
            rows[recommendation["recommendation_id"]] = recommendation
    return rows


def _target(recommendation: dict) -> dict:
    task = str(recommendation.get("task") or "").strip().upper()
    campaign_id = str(recommendation.get("campaign_id") or "").strip() or None
    media_id = str(recommendation.get("creative_media_id") or "").strip() or None
    if task == "CREATIVE" and media_id:
        return {"kind": "CREATIVE", "id": media_id, "campaign_id": campaign_id, "media_id": media_id}
    if campaign_id:
        return {"kind": "CAMPAIGN", "id": campaign_id, "campaign_id": campaign_id, "media_id": media_id}
    return {"kind": "UNKNOWN", "id": None, "campaign_id": campaign_id, "media_id": media_id}


def _matches_target(row: dict, target: dict) -> bool:
    if target["kind"] == "CREATIVE":
        return str(row.get("creative_media_id") or "").strip() == target["media_id"]
    if target["kind"] == "CAMPAIGN":
        return str(row.get("campaign_id") or "").strip() == target["campaign_id"]
    return False


def _safe_metrics(value: object) -> dict:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int | float] = {}
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            continue
        result[str(key)[:80]] = raw
    return result


def _snapshot_observation(snapshot: object, target: dict) -> dict:
    snap = _payload(snapshot)
    social = snap.get("social") if isinstance(snap.get("social"), dict) else {}
    paid = snap.get("paid_media") if isinstance(snap.get("paid_media"), dict) else {}
    organic_rows: list[dict] = []
    paid_rows: list[dict] = []
    for row in social.get("observations") or []:
        if not isinstance(row, dict) or not _matches_target(row, target):
            continue
        metrics = _safe_metrics(row.get("metrics"))
        if metrics:
            organic_rows.append({
                "publication_id": row.get("publication_id"),
                "channel": row.get("channel"),
                "metrics": metrics,
            })
    for row in paid.get("observations") or []:
        if not isinstance(row, dict) or not _matches_target(row, target):
            continue
        metrics = _safe_metrics(row.get("metrics"))
        if metrics:
            paid_rows.append({
                "draft_id": row.get("draft_id"),
                "currency": row.get("currency"),
                "metrics": metrics,
            })
    return {
        "snapshot_id": snap.get("id"),
        "created_at": snap.get("created_at"),
        "date_preset": snap.get("date_preset"),
        "organic_observations": len(organic_rows),
        "paid_observations": len(paid_rows),
        "organic_samples": organic_rows[:3],
        "paid_samples": paid_rows[:3],
        "has_target_signal": bool(organic_rows or paid_rows),
        "snapshot_captured_after_application": True,
        "metric_window_strictly_post_application": False,
    }


def project_recommendation_evidence(
    company_id: str,
    *,
    sessions: Iterable[object],
    resolutions: Iterable[RecommendationHandoffResolution],
    snapshots: Iterable[object],
    now: datetime | None = None,
) -> dict:
    company = _company(company_id)
    current = _utc(now)
    recommendation_by_id = _historical_recommendations(sessions)
    snapshot_rows = list(snapshots)
    snapshot_rows.sort(key=lambda row: str(_value(row, "created_at") or ""), reverse=True)

    tracked: list[dict] = []
    not_applied = 0
    identity_gaps = 0
    for resolution in resolutions:
        if resolution.company_id != company:
            continue
        if resolution.outcome != "APPLIED":
            not_applied += 1
            continue
        recommendation = recommendation_by_id.get(resolution.recommendation_id)
        if (
            recommendation is None
            or recommendation.get("session_id") != resolution.session_id
            or recommendation.get("recommendation_sha256") != resolution.recommendation_sha256
        ):
            identity_gaps += 1
            tracked.append({
                "recommendation_id": resolution.recommendation_id,
                "session_id": resolution.session_id,
                "applied_at": resolution.resolved_at,
                "followup_due_at": None,
                "state": "IDENTITY_GAP",
                "state_reason": "La resolución existe, pero la sesión/recomendación histórica exacta ya no está disponible para reconstruir el objetivo sin inferencias.",
                "target": {"kind": "UNKNOWN", "id": None, "campaign_id": None, "media_id": None},
                "route": {"state": "OWNER_GAP", "view": None, "owner": None},
                "post_application_snapshot": None,
                "age_seconds": None,
            })
            continue

        route = _route(recommendation)
        target = _target(recommendation)
        applied = _timestamp(resolution.resolved_at)
        followup_due_at = None if applied is None else (applied + timedelta(seconds=FOLLOWUP_WINDOW_SECONDS)).isoformat()
        age_seconds = None if applied is None or applied > current else int((current - applied).total_seconds())
        post_snapshots = []
        if applied is not None:
            for snapshot in snapshot_rows:
                created = _timestamp(_value(snapshot, "created_at"))
                if created is not None and created > applied:
                    post_snapshots.append(snapshot)

        observations = [_snapshot_observation(snapshot, target) for snapshot in post_snapshots]
        with_signal = [row for row in observations if row["has_target_signal"]]
        if applied is None or applied > current:
            state = "INVALID_APPLIED_TIME"
            reason = "La marca temporal de aplicación no permite ordenar evidencia posterior de forma confiable."
            selected = None
        elif with_signal:
            state = "EVIDENCE_AVAILABLE"
            reason = "Existe un snapshot capturado después del cierre humano con señal de marketing para la identidad estructurada exacta. Su ventana de métricas puede incluir tiempo anterior a la aplicación."
            selected = with_signal[0]
        elif post_snapshots:
            state = "POST_SNAPSHOT_NO_TARGET_SIGNAL"
            reason = "Existe al menos un snapshot capturado después del cierre, pero no contiene métricas observadas para la campaña/creativo exacto."
            selected = observations[0] if observations else None
        elif age_seconds is not None and age_seconds >= FOLLOWUP_WINDOW_SECONDS:
            state = "CAPTURE_DUE"
            reason = "Han pasado 24 horas desde el cierre como aplicado y todavía no existe un snapshot posterior; corresponde capturar resultados manualmente."
            selected = None
        else:
            state = "OBSERVATION_WINDOW"
            reason = "El handoff fue marcado como aplicado hace menos de 24 horas; aún no se exige una nueva captura de resultados."
            selected = None

        tracked.append({
            "recommendation_id": resolution.recommendation_id,
            "session_id": resolution.session_id,
            "recommendation_sha256": resolution.recommendation_sha256,
            "title": recommendation.get("title"),
            "area": recommendation.get("area"),
            "task": recommendation.get("task"),
            "applied_at": resolution.resolved_at,
            "followup_due_at": followup_due_at,
            "age_seconds": age_seconds,
            "state": state,
            "state_reason": reason,
            "target": target,
            "route": route,
            "post_application_snapshot": selected,
            "post_snapshot_count": len(post_snapshots),
            "post_snapshots_with_target_signal": len(with_signal),
            "causal_attribution": False,
        })

    tracked.sort(key=lambda row: (str(row.get("applied_at") or ""), row["recommendation_id"]), reverse=True)
    visible = tracked[:MAX_TRACKED_RECOMMENDATIONS]
    state_counts: dict[str, int] = {}
    for row in tracked:
        state_counts[row["state"]] = state_counts.get(row["state"], 0) + 1
    return {
        "schema": AI_RECOMMENDATION_EVIDENCE_SCHEMA,
        "company_id": company,
        "projected_at": current.isoformat(),
        "summary": {
            "tracked_applied": len(tracked),
            "not_applied": not_applied,
            "evidence_available": state_counts.get("EVIDENCE_AVAILABLE", 0),
            "capture_due": state_counts.get("CAPTURE_DUE", 0),
            "observation_window": state_counts.get("OBSERVATION_WINDOW", 0),
            "post_snapshot_no_target_signal": state_counts.get("POST_SNAPSHOT_NO_TARGET_SIGNAL", 0),
            "identity_gaps": identity_gaps,
            "by_state": state_counts,
        },
        "recommendations": visible,
        "contracts": {
            "applied_means_operator_marked_handoff_closed": True,
            "applied_does_not_prove_business_execution": True,
            "post_application_evidence_is_observational": True,
            "snapshot_capture_after_applied_does_not_bound_metric_event_time": True,
            "causal_attribution_to_ai": False,
            "historical_session_identity_required": True,
            "exact_structured_target_required": True,
            "followup_window_seconds": FOLLOWUP_WINDOW_SECONDS,
            "automatic_provider_refresh": False,
        },
        "safety": {
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "ai_generation_performed": False,
            "business_mutation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }


def _rank(row: dict) -> int:
    value = row.get("rank")
    return value if isinstance(value, int) and not isinstance(value, bool) else 999


def _queue_key(row: dict) -> tuple:
    return (
        _rank(row),
        action_base._URGENCY_ORDER.get(str(row.get("urgency") or "").upper(), 9),
        row.get("due_at") is None,
        str(row.get("due_at") or ""),
        str(row.get("id") or ""),
    )


def _existing_capture_for_target(queue: list[dict], target: dict) -> bool:
    for row in queue:
        reason = row.get("reason") or {}
        action = row.get("action") or {}
        if str(reason.get("code") or "").upper() != "CAMPAIGN_CAPTURE_RESULTS":
            continue
        if target.get("campaign_id") and action.get("campaign_id") == target.get("campaign_id"):
            return True
    return False


def extend_action_center(payload: dict, evidence: dict) -> dict:
    """Add only overdue evidence-capture work, shadowing existing campaign capture tasks."""
    result = deepcopy(payload)
    queue = list(result.get("queue") or [])
    added = 0
    shadowed = 0
    for row in evidence.get("recommendations") or []:
        if row.get("state") != "CAPTURE_DUE":
            continue
        target = row.get("target") or {}
        if _existing_capture_for_target(queue, target):
            shadowed += 1
            continue
        task = action_base._item(
            rank=88,
            urgency="LOW",
            source="AI_EVIDENCE",
            kind="ai_recommendation_evidence_capture",
            title=f"Capturar evidencia posterior · {row.get('title') or 'recomendación de Astra'}",
            detail="El handoff fue marcado como aplicado hace al menos 24 h y no hay snapshot posterior. Captura resultados; la app no atribuirá causalidad a Astra.",
            action_label="Actualizar resultados",
            view="analytics",
            tab="ai-recommendation-evidence",
            entity_id=row.get("recommendation_id"),
            campaign_id=target.get("campaign_id"),
            media_id=target.get("media_id"),
            due_at=row.get("followup_due_at"),
            reason_code="AI_RECOMMENDATION_POST_APPLICATION_CAPTURE_DUE",
            reason="La captura sirve para observar qué ocurrió después del cierre humano. No demuestra que la recomendación ni Astra causaran el resultado.",
        )
        task["ai_evidence"] = {
            "recommendation_id": row.get("recommendation_id"),
            "target_kind": target.get("kind"),
            "target_id": target.get("id"),
            "causal_attribution": False,
        }
        queue.append(task)
        added += 1

    deduped: dict[str, dict] = {}
    for row in queue:
        identity = str(row.get("id") or "")
        existing = deduped.get(identity)
        if existing is None or _queue_key(row) < _queue_key(existing):
            deduped[identity] = row
    queue = sorted(deduped.values(), key=_queue_key)[:50]
    result["queue"] = queue
    result["next_action"] = queue[0] if queue else None
    result["focus"] = {
        "now": [row for row in queue if row.get("urgency") in {"CRITICAL", "HIGH"}][:8],
        "next": [row for row in queue if row.get("urgency") == "MEDIUM"][:8],
        "later": [row for row in queue if row.get("urgency") == "LOW"][:8],
    }
    by_source: dict[str, int] = {}
    by_urgency = {key: 0 for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    for row in queue:
        source = str(row.get("source") or "UNKNOWN")
        by_source[source] = by_source.get(source, 0) + 1
        urgency = str(row.get("urgency") or "").upper()
        if urgency in by_urgency:
            by_urgency[urgency] += 1
    summary = result.setdefault("summary", {})
    summary.update({
        "queue_total": len(queue),
        "blocking": sum(bool(row.get("blocking")) for row in queue),
        "critical": by_urgency["CRITICAL"],
        "high": by_urgency["HIGH"],
        "medium": by_urgency["MEDIUM"],
        "low": by_urgency["LOW"],
        "by_source": by_source,
        "ai_evidence_capture_added": added,
        "ai_evidence_capture_shadowed": shadowed,
    })
    result.setdefault("contracts", {})["ai_post_application_observation"] = True
    result.setdefault("safety", {})["ai_evidence_causal_attribution"] = False
    return result


__all__ = [
    "AI_RECOMMENDATION_EVIDENCE_SCHEMA",
    "FOLLOWUP_WINDOW_SECONDS",
    "MAX_TRACKED_RECOMMENDATIONS",
    "extend_action_center",
    "project_recommendation_evidence",
]
