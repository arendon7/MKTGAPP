from __future__ import annotations

import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from . import service_post_w99_action_center_app as action_base
from .ai_recommendation_review import RecommendationReview, current_recommendations
from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now


AI_RECOMMENDATION_HANDOFF_SCHEMA = "binario.marketing.ai-recommendation-handoff-resolution.v1"
AI_RECOMMENDATION_HANDOFF_PROJECTION_SCHEMA = "binario.marketing.ai-recommendation-handoff-projection.v1"
HANDOFF_OUTCOMES = {"APPLIED", "NOT_APPLIED"}
RECOMMENDATION_ID_RE = re.compile(r"^airec_[0-9a-f]{24}$")
MAX_OPEN_HANDOFFS = 12


class RecommendationHandoffConflict(ValueError):
    pass


def _company(value: object) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def _route(row: dict) -> dict:
    """Resolve an owner only from structured identity, never from AI prose."""
    task = str(row.get("task") or "").strip().upper()
    area = str(row.get("area") or "STRATEGY").strip().upper()
    campaign_id = str(row.get("campaign_id") or "").strip() or None
    media_id = str(row.get("creative_media_id") or "").strip() or None

    if task == "CAMPAIGN" and campaign_id:
        if area in {"CAMPAIGN", "STRATEGY"}:
            return {
                "state": "OWNER_RESOLVED", "view": "campaigns", "tab": "ai-accepted-handoff",
                "campaign_id": campaign_id, "media_id": None,
                "owner": "Campaign Center",
                "reason": "La recomendación pertenece a una campaña exacta y su área es estrategia/campaña.",
            }
        if area in {"CONTENT", "CREATIVE", "PAID_MEDIA"}:
            return {
                "state": "OWNER_RESOLVED", "view": "execution", "tab": "ai-accepted-handoff",
                "campaign_id": campaign_id, "media_id": media_id,
                "owner": "Execution Workspace",
                "reason": "La campaña exacta existe; Execution Workspace conserva la coordinación canónica hacia creativo, distribución o pauta.",
            }

    if task == "CREATIVE" and media_id:
        if area in {"CONTENT", "CREATIVE"}:
            return {
                "state": "OWNER_RESOLVED", "view": "content", "tab": "ai-accepted-handoff",
                "campaign_id": campaign_id, "media_id": media_id,
                "owner": "Contenido",
                "reason": "La recomendación identifica un activo creativo exacto.",
            }
        if campaign_id and area in {"CAMPAIGN", "STRATEGY"}:
            return {
                "state": "OWNER_RESOLVED", "view": "campaigns", "tab": "ai-accepted-handoff",
                "campaign_id": campaign_id, "media_id": media_id,
                "owner": "Campaign Center",
                "reason": "La recomendación creativa referencia una campaña exacta pero pide trabajo de campaña/estrategia.",
            }
        if campaign_id and area == "PAID_MEDIA":
            return {
                "state": "OWNER_RESOLVED", "view": "execution", "tab": "ai-accepted-handoff",
                "campaign_id": campaign_id, "media_id": media_id,
                "owner": "Execution Workspace",
                "reason": "La recomendación creativa referencia una campaña exacta y pauta; Execution Workspace mantiene el siguiente owner canónico.",
            }

    return {
        "state": "OWNER_GAP", "view": None, "tab": None,
        "campaign_id": campaign_id, "media_id": media_id, "owner": None,
        "reason": "No existe identidad estructurada suficiente para escoger un módulo dueño sin inferir desde texto libre de la IA.",
    }


@dataclass(frozen=True)
class RecommendationHandoffResolution:
    schema: str
    company_id: str
    recommendation_id: str
    session_id: str
    recommendation_sha256: str
    outcome: str
    resolved_at: str


class RecommendationHandoffStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _folder(self, company_id: str) -> Path:
        folder = self.root / _company(company_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _path(self, company_id: str, recommendation_id: str) -> Path:
        if not RECOMMENDATION_ID_RE.fullmatch(str(recommendation_id or "")):
            raise ValueError("invalid AI recommendation id")
        return self._folder(company_id) / f"{recommendation_id}.json"

    def get(self, company_id: str, recommendation_id: str) -> RecommendationHandoffResolution | None:
        path = self._path(company_id, recommendation_id)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != AI_RECOMMENDATION_HANDOFF_SCHEMA:
            raise ValueError("invalid AI recommendation handoff resolution")
        row = RecommendationHandoffResolution(**payload)
        if row.company_id != _company(company_id) or row.recommendation_id != recommendation_id:
            raise ValueError("AI recommendation handoff identity mismatch")
        return row

    def list(self, company_id: str) -> list[RecommendationHandoffResolution]:
        company = _company(company_id)
        rows: list[RecommendationHandoffResolution] = []
        for path in self._folder(company).glob("airec_*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                row = RecommendationHandoffResolution(**payload)
                if row.schema == AI_RECOMMENDATION_HANDOFF_SCHEMA and row.company_id == company:
                    rows.append(row)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(rows, key=lambda row: (row.resolved_at, row.recommendation_id), reverse=True)

    def record(self, company_id: str, *, recommendation_id: str, session_id: str, digest: str, outcome: str) -> RecommendationHandoffResolution:
        company = _company(company_id)
        rec_id = str(recommendation_id or "").strip()
        if not RECOMMENDATION_ID_RE.fullmatch(rec_id):
            raise ValueError("invalid AI recommendation id")
        session = str(session_id or "").strip()
        if not re.fullmatch(r"ai_[0-9a-f]{24}", session):
            raise ValueError("invalid AI session id")
        digest_value = str(digest or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest_value):
            raise ValueError("invalid AI recommendation sha256")
        outcome_value = str(outcome or "").strip().upper()
        if outcome_value not in HANDOFF_OUTCOMES:
            raise ValueError("AI recommendation handoff outcome must be APPLIED or NOT_APPLIED")
        existing = self.get(company, rec_id)
        if existing is not None:
            if existing.session_id == session and existing.recommendation_sha256 == digest_value and existing.outcome == outcome_value:
                return existing
            raise RecommendationHandoffConflict("AI recommendation handoff was already resolved")
        row = RecommendationHandoffResolution(
            schema=AI_RECOMMENDATION_HANDOFF_SCHEMA,
            company_id=company,
            recommendation_id=rec_id,
            session_id=session,
            recommendation_sha256=digest_value,
            outcome=outcome_value,
            resolved_at=_now(),
        )
        write_json_atomic(self._path(company, rec_id), asdict(row))
        return row


def project_recommendation_handoffs(
    company_id: str,
    *,
    sessions: Iterable[object],
    reviews: Iterable[RecommendationReview],
    resolutions: Iterable[RecommendationHandoffResolution],
) -> dict:
    company = _company(company_id)
    current = current_recommendations(sessions)
    review_by_id = {row.recommendation_id: row for row in reviews}
    resolution_by_id = {row.recommendation_id: row for row in resolutions}
    open_rows: list[dict] = []
    resolved_current: list[dict] = []
    owner_gaps: list[dict] = []

    for rec in current:
        review = review_by_id.get(rec["recommendation_id"])
        if review is None or review.decision != "ACCEPTED":
            continue
        if review.session_id != rec["session_id"] or review.recommendation_sha256 != rec["recommendation_sha256"]:
            continue
        route = _route(rec)
        payload = {**rec, "route": route, "accepted_at": review.decided_at}
        resolution = resolution_by_id.get(rec["recommendation_id"])
        if resolution is not None:
            if resolution.session_id == rec["session_id"] and resolution.recommendation_sha256 == rec["recommendation_sha256"]:
                resolved_current.append({**payload, "resolution": asdict(resolution)})
            continue
        if route["state"] == "OWNER_RESOLVED":
            open_rows.append(payload)
        else:
            owner_gaps.append(payload)

    open_rows.sort(key=lambda row: (str(row.get("accepted_at") or ""), row["recommendation_id"]), reverse=True)
    owner_gaps.sort(key=lambda row: (str(row.get("accepted_at") or ""), row["recommendation_id"]), reverse=True)
    return {
        "schema": AI_RECOMMENDATION_HANDOFF_PROJECTION_SCHEMA,
        "company_id": company,
        "summary": {
            "open_handoffs": len(open_rows),
            "owner_gaps": len(owner_gaps),
            "resolved_current": len(resolved_current),
            "applied_current": sum((row.get("resolution") or {}).get("outcome") == "APPLIED" for row in resolved_current),
            "not_applied_current": sum((row.get("resolution") or {}).get("outcome") == "NOT_APPLIED" for row in resolved_current),
        },
        "handoffs": open_rows[:MAX_OPEN_HANDOFFS],
        "owner_gaps": owner_gaps[:MAX_OPEN_HANDOFFS],
        "resolved": resolved_current[:MAX_OPEN_HANDOFFS],
        "contracts": {
            "accepted_review_required": True,
            "current_recommendation_identity_required": True,
            "owner_from_structured_fields_only": True,
            "free_text_owner_inference": False,
            "handoff_resolution_is_local_evidence_only": True,
        },
        "safety": {
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


def extend_action_center(payload: dict, handoffs: dict) -> dict:
    """Project unresolved accepted recommendations as low-priority owner handoffs."""
    result = deepcopy(payload)
    queue = list(result.get("queue") or [])
    for row in handoffs.get("handoffs") or []:
        route = row.get("route") or {}
        if route.get("state") != "OWNER_RESOLVED" or not route.get("view"):
            continue
        task = action_base._item(
            rank=87,
            urgency="LOW",
            source="AI_HANDOFF",
            kind="ai_accepted_handoff",
            title=f"Aplicar manualmente recomendación aceptada · {row.get('title') or 'Astra'}",
            detail=f"Owner: {route.get('owner') or 'módulo canónico'}. Astra no ejecutó nada; abre el owner exacto y decide allí cómo aplicar la recomendación.",
            action_label="Abrir módulo responsable",
            view=str(route.get("view")),
            tab=str(route.get("tab") or "ai-accepted-handoff"),
            entity_id=str(row.get("recommendation_id") or ""),
            campaign_id=route.get("campaign_id"),
            media_id=route.get("media_id"),
            due_at=row.get("accepted_at"),
            reason_code="AI_ACCEPTED_RECOMMENDATION_HANDOFF",
            reason="La recomendación fue aceptada explícitamente por una persona. El handoff sólo navega al owner estructurado; no elige controles ni ejecuta cambios.",
        )
        task["ai_handoff"] = {
            "recommendation_id": row.get("recommendation_id"),
            "session_id": row.get("session_id"),
            "area": row.get("area"),
            "owner": route.get("owner"),
            "structured_owner_only": True,
        }
        queue.append(task)

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
        "critical": by_urgency["CRITICAL"], "high": by_urgency["HIGH"],
        "medium": by_urgency["MEDIUM"], "low": by_urgency["LOW"],
        "by_source": by_source,
    })
    result.setdefault("contracts", {})["accepted_ai_owner_handoff"] = True
    result.setdefault("safety", {})["ai_handoff_executes_business_action"] = False
    return result


__all__ = [
    "AI_RECOMMENDATION_HANDOFF_PROJECTION_SCHEMA",
    "AI_RECOMMENDATION_HANDOFF_SCHEMA",
    "HANDOFF_OUTCOMES",
    "RecommendationHandoffConflict",
    "RecommendationHandoffResolution",
    "RecommendationHandoffStore",
    "extend_action_center",
    "project_recommendation_handoffs",
]
