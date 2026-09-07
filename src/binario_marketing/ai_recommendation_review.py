from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from . import service_post_w99_action_center_app as action_base
from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now


AI_RECOMMENDATION_REVIEW_SCHEMA = "binario.marketing.ai-recommendation-review.v1"
AI_RECOMMENDATION_PROJECTION_SCHEMA = "binario.marketing.ai-recommendation-review-projection.v1"
RECOMMENDATION_ID_RE = re.compile(r"^airec_[0-9a-f]{24}$")
REVIEW_DECISIONS = {"ACCEPTED", "DISMISSED"}
MAX_CURRENT_SESSIONS = 12
MAX_RECOMMENDATIONS_PER_SESSION = 5
MAX_PENDING_RECOMMENDATIONS = 30


class RecommendationReviewConflict(ValueError):
    pass


def _company(value: object) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def _text(value: object, limit: int) -> str:
    return " ".join(str(value or "").strip().split())[:limit]


def _session_value(session: object, name: str, default=None):
    if isinstance(session, dict):
        return session.get(name, default)
    return getattr(session, name, default)


def _recommendation_payload(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    title = _text(value.get("title"), 220)
    next_step = _text(value.get("next_step"), 700)
    if not title or not next_step:
        return None
    priority = _text(value.get("priority"), 12).upper()
    if priority not in {"HIGH", "MEDIUM", "LOW"}:
        priority = "MEDIUM"
    area = _text(value.get("area"), 32).upper()
    if area not in {"STRATEGY", "CAMPAIGN", "CREATIVE", "PAID_MEDIA", "CRM", "CONTENT"}:
        area = "STRATEGY"
    return {
        "title": title,
        "why": _text(value.get("why"), 1200),
        "priority": priority,
        "area": area,
        "next_step": next_step,
    }


def recommendation_sha256(value: dict) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def recommendation_id(session_id: str, index: int, digest: str) -> str:
    identity = f"{session_id}:{int(index)}:{digest}".encode("utf-8")
    return "airec_" + hashlib.sha256(identity).hexdigest()[:24]


def _target_key(session: object) -> tuple[str, str, str]:
    return (
        str(_session_value(session, "task") or "").strip().upper(),
        str(_session_value(session, "campaign_id") or "").strip(),
        str(_session_value(session, "creative_media_id") or "").strip(),
    )


def _target_label(session: object) -> str:
    task, campaign_id, creative_media_id = _target_key(session)
    context = _session_value(session, "context", {})
    context = context if isinstance(context, dict) else {}
    if task == "CAMPAIGN":
        selected = context.get("selected_campaign") if isinstance(context.get("selected_campaign"), dict) else {}
        return _text(selected.get("name"), 220) or campaign_id or "Campaña"
    if task == "CREATIVE":
        selected = context.get("selected_creative") if isinstance(context.get("selected_creative"), dict) else {}
        return _text(selected.get("title"), 220) or creative_media_id or "Creativo"
    return "Estrategia de empresa"


def current_recommendations(sessions: Iterable[object]) -> list[dict]:
    """Return recommendations only from the latest session for each exact AI target."""
    latest: list[object] = []
    seen: set[tuple[str, str, str]] = set()
    for session in sessions:
        key = _target_key(session)
        if not key[0] or key in seen:
            continue
        seen.add(key)
        latest.append(session)
        if len(latest) >= MAX_CURRENT_SESSIONS:
            break

    rows: list[dict] = []
    for session in latest:
        session_id = str(_session_value(session, "id") or "").strip()
        output = _session_value(session, "output", {})
        output = output if isinstance(output, dict) else {}
        task, campaign_id, creative_media_id = _target_key(session)
        for index, raw in enumerate((output.get("recommendations") or [])[:MAX_RECOMMENDATIONS_PER_SESSION]):
            recommendation = _recommendation_payload(raw)
            if recommendation is None:
                continue
            digest = recommendation_sha256(recommendation)
            rows.append({
                "recommendation_id": recommendation_id(session_id, index, digest),
                "recommendation_sha256": digest,
                "session_id": session_id,
                "recommendation_index": index,
                "session_created_at": str(_session_value(session, "created_at") or "").strip() or None,
                "task": task,
                "campaign_id": campaign_id or None,
                "creative_media_id": creative_media_id or None,
                "target_label": _target_label(session),
                **recommendation,
            })
            if len(rows) >= MAX_PENDING_RECOMMENDATIONS:
                return rows
    return rows


@dataclass(frozen=True)
class RecommendationReview:
    schema: str
    company_id: str
    recommendation_id: str
    session_id: str
    recommendation_sha256: str
    decision: str
    decided_at: str


class RecommendationReviewStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _folder(self, company_id: str) -> Path:
        folder = self.root / _company(company_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _path(self, company_id: str, recommendation: str) -> Path:
        if not RECOMMENDATION_ID_RE.fullmatch(str(recommendation or "")):
            raise ValueError("invalid AI recommendation id")
        return self._folder(company_id) / f"{recommendation}.json"

    def get(self, company_id: str, recommendation: str) -> RecommendationReview | None:
        path = self._path(company_id, recommendation)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != AI_RECOMMENDATION_REVIEW_SCHEMA:
            raise ValueError("invalid AI recommendation review")
        row = RecommendationReview(**payload)
        if row.company_id != _company(company_id) or row.recommendation_id != recommendation:
            raise ValueError("AI recommendation review identity mismatch")
        return row

    def list(self, company_id: str) -> list[RecommendationReview]:
        company = _company(company_id)
        rows: list[RecommendationReview] = []
        for path in self._folder(company).glob("airec_*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                row = RecommendationReview(**payload)
                if row.schema == AI_RECOMMENDATION_REVIEW_SCHEMA and row.company_id == company:
                    rows.append(row)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
        return sorted(rows, key=lambda row: (row.decided_at, row.recommendation_id), reverse=True)

    def record(
        self,
        company_id: str,
        *,
        recommendation: str,
        session_id: str,
        digest: str,
        decision: str,
    ) -> RecommendationReview:
        company = _company(company_id)
        rec_id = str(recommendation or "").strip()
        if not RECOMMENDATION_ID_RE.fullmatch(rec_id):
            raise ValueError("invalid AI recommendation id")
        session = str(session_id or "").strip()
        if not re.fullmatch(r"ai_[0-9a-f]{24}", session):
            raise ValueError("invalid AI session id")
        digest_value = str(digest or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest_value):
            raise ValueError("invalid AI recommendation sha256")
        decision_value = str(decision or "").strip().upper()
        if decision_value not in REVIEW_DECISIONS:
            raise ValueError("unsupported AI recommendation review decision")
        existing = self.get(company, rec_id)
        if existing is not None:
            if (
                existing.session_id == session
                and existing.recommendation_sha256 == digest_value
                and existing.decision == decision_value
            ):
                return existing
            raise RecommendationReviewConflict("AI recommendation was already reviewed")
        row = RecommendationReview(
            schema=AI_RECOMMENDATION_REVIEW_SCHEMA,
            company_id=company,
            recommendation_id=rec_id,
            session_id=session,
            recommendation_sha256=digest_value,
            decision=decision_value,
            decided_at=_now(),
        )
        write_json_atomic(self._path(company, rec_id), asdict(row))
        return row


def project_recommendation_review(
    company_id: str,
    *,
    sessions: Iterable[object],
    reviews: Iterable[RecommendationReview],
) -> dict:
    company = _company(company_id)
    current = current_recommendations(sessions)
    review_by_id = {row.recommendation_id: row for row in reviews}
    pending = [row for row in current if row["recommendation_id"] not in review_by_id]
    groups: list[dict] = []
    by_session: dict[str, list[dict]] = {}
    for row in pending:
        by_session.setdefault(row["session_id"], []).append(row)
    for session_id, rows in by_session.items():
        first = rows[0]
        groups.append({
            "session_id": session_id,
            "session_created_at": first.get("session_created_at"),
            "task": first.get("task"),
            "campaign_id": first.get("campaign_id"),
            "creative_media_id": first.get("creative_media_id"),
            "target_label": first.get("target_label"),
            "pending_count": len(rows),
            "suggested_priorities": sorted({str(row.get("priority") or "MEDIUM") for row in rows}),
            "areas": sorted({str(row.get("area") or "STRATEGY") for row in rows}),
            "recommendations": rows,
        })
    groups.sort(key=lambda row: (str(row.get("session_created_at") or ""), row["session_id"]), reverse=True)
    decisions = list(reviews)
    return {
        "schema": AI_RECOMMENDATION_PROJECTION_SCHEMA,
        "company_id": company,
        "summary": {
            "current_sessions_with_pending_review": len(groups),
            "pending_recommendations": len(pending),
            "accepted": sum(row.decision == "ACCEPTED" for row in decisions),
            "dismissed": sum(row.decision == "DISMISSED" for row in decisions),
        },
        "groups": groups,
        "contracts": {
            "latest_session_per_exact_target_only": True,
            "ai_priority_is_context_only": True,
            "review_does_not_execute_recommendation": True,
            "no_ai_generation_on_read": True,
            "no_provider_read_on_read": True,
        },
        "safety": {
            "ai_generation_performed": False,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
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


def extend_action_center(payload: dict, review: dict) -> dict:
    """Add one low-priority human review task per current AI session, never per recommendation."""
    result = deepcopy(payload)
    groups = list(review.get("groups") or [])
    pending_campaigns = {str(row.get("campaign_id") or "") for row in groups if row.get("campaign_id")}
    queue = []
    for row in result.get("queue") or []:
        if str(row.get("kind") or "") == "optional_ai" and str((row.get("action") or {}).get("campaign_id") or "") in pending_campaigns:
            continue
        queue.append(row)

    for group in groups:
        count = int(group.get("pending_count") or 0)
        if count <= 0:
            continue
        task = action_base._item(
            rank=86,
            urgency="LOW",
            source="AI_REVIEW",
            kind="ai_recommendation_review",
            title=f"Revisar {count} recomendación{'es' if count != 1 else ''} de Astra · {group.get('target_label') or 'IA'}",
            detail="La IA propuso próximos pasos. Su prioridad es sólo contexto: acepta o descarta cada recomendación antes de usarla.",
            action_label="Revisar en Astra / IA",
            view="intelligence",
            tab="ai-recommendation-review",
            entity_id=str(group.get("session_id") or ""),
            campaign_id=group.get("campaign_id"),
            media_id=group.get("creative_media_id"),
            due_at=group.get("session_created_at"),
            reason_code="AI_RECOMMENDATION_REVIEW_PENDING",
            reason="La sesión IA ya fue generada por acción humana. Action Center sólo eleva su revisión; no acepta, descarta ni ejecuta recomendaciones automáticamente.",
        )
        task["ai_context"] = {
            "pending_count": count,
            "suggested_priorities": list(group.get("suggested_priorities") or []),
            "areas": list(group.get("areas") or []),
            "priority_is_non_authoritative": True,
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
        "critical": by_urgency["CRITICAL"],
        "high": by_urgency["HIGH"],
        "medium": by_urgency["MEDIUM"],
        "low": by_urgency["LOW"],
        "by_source": by_source,
        "ai_review_sessions": len(groups),
        "ai_review_pending_recommendations": int((review.get("summary") or {}).get("pending_recommendations") or 0),
    })
    result.setdefault("contracts", {}).update({
        "ai_recommendation_review_is_human_only": True,
        "ai_priority_never_changes_action_center_priority": True,
    })
    result.setdefault("safety", {}).update({
        "ai_review_generation_performed": False,
        "ai_review_business_execution_performed": False,
    })
    result["ai_recommendation_review"] = {
        "pending_sessions": len(groups),
        "pending_recommendations": int((review.get("summary") or {}).get("pending_recommendations") or 0),
    }
    return result


__all__ = [
    "AI_RECOMMENDATION_PROJECTION_SCHEMA",
    "AI_RECOMMENDATION_REVIEW_SCHEMA",
    "RecommendationReview",
    "RecommendationReviewConflict",
    "RecommendationReviewStore",
    "current_recommendations",
    "extend_action_center",
    "project_recommendation_review",
    "recommendation_id",
    "recommendation_sha256",
]
