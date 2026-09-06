from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable

from . import service_post_w99_action_center_app as action_base
from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE


SNAPSHOT_SCHEMA = "binario.marketing.inbox-attention-snapshot.v1"
ATTENTION_SCHEMA = "binario.marketing.inbox-attention.v1"
STALE_AFTER = timedelta(hours=12)
MAX_ITEMS = 40
MAX_EXCERPT = 280
_STAGE_ORDER = {"SENT": 0, "SENDING": 1, "AMBIGUOUS": 2}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: object) -> datetime | None:
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


def _text(value: object, limit: int) -> str | None:
    raw = " ".join(str(value or "").strip().split())
    return raw[:limit] or None


def _handle(person: object) -> str | None:
    if not isinstance(person, dict):
        return None
    value = str(person.get("username") or "").strip().lstrip("@").casefold()
    return value[:120] or None


def _contact_id(value: object) -> str | None:
    if not isinstance(value, dict):
        return None
    contact_id = str(value.get("id") or "").strip()
    return contact_id if contact_id.startswith("contact_") else None


def _incoming(page_id: str | None, message: dict) -> bool:
    page = str(page_id or "").strip()
    sender = message.get("from")
    sender_id = str(sender.get("id") or "").strip() if isinstance(sender, dict) else ""
    recipients = message.get("to") if isinstance(message.get("to"), list) else []
    recipient_ids = {
        str(row.get("id") or "").strip()
        for row in recipients if isinstance(row, dict)
    }
    return bool(page and sender_id and sender_id != page and page in recipient_ids and not message.get("unavailable"))


def build_snapshot(
    company_id: str,
    *,
    page_id: str | None,
    instagram_id: str | None,
    payload: dict,
    captured_at: datetime | None = None,
) -> dict:
    """Minimize one explicit Meta refresh into local, secret-free attention evidence."""
    company = str(company_id or "").strip()
    if not COMPANY_ID_RE.fullmatch(company):
        raise ValueError("invalid company id")
    if not isinstance(payload, dict):
        raise ValueError("social inbox payload must be an object")

    items: list[dict] = []
    skipped = 0
    if bool(payload.get("configured")):
        for conversation in payload.get("conversations") or []:
            if not isinstance(conversation, dict):
                continue
            messages = [row for row in (conversation.get("messages") or []) if isinstance(row, dict)]
            messages.sort(key=lambda row: str(row.get("created_time") or ""), reverse=True)
            if not messages or not _incoming(page_id, messages[0]):
                continue
            row = messages[0]
            interaction_id = str(row.get("id") or "").strip()
            occurred = _parse(row.get("created_time"))
            if not interaction_id or occurred is None:
                skipped += 1
                continue
            items.append({
                "kind": "facebook_message",
                "interaction_id": interaction_id[:300],
                "occurred_at": _iso(occurred),
                "actor_handle": _handle(row.get("from")),
                "crm_contact_id": _contact_id(row.get("crm_contact")),
                "excerpt": _text(row.get("message"), MAX_EXCERPT),
                "reply_eligible": bool(row.get("reply_eligible")),
            })

        instagram = str(instagram_id or "").strip()
        for row in payload.get("comments") or []:
            if not isinstance(row, dict):
                continue
            interaction_id = str(row.get("id") or "").strip()
            occurred = _parse(row.get("timestamp"))
            author = row.get("from")
            author_id = str(author.get("id") or "").strip() if isinstance(author, dict) else ""
            if not interaction_id or occurred is None or (instagram and author_id == instagram):
                if interaction_id and occurred is None:
                    skipped += 1
                continue
            items.append({
                "kind": "instagram_comment",
                "interaction_id": interaction_id[:300],
                "occurred_at": _iso(occurred),
                "actor_handle": _handle(author),
                "crm_contact_id": _contact_id(row.get("crm_contact")),
                "excerpt": _text(row.get("text"), MAX_EXCERPT),
                "reply_eligible": bool(row.get("reply_eligible")),
            })

    items.sort(key=lambda row: (row["occurred_at"], row["kind"], row["interaction_id"]), reverse=True)
    items = items[:MAX_ITEMS]
    return {
        "schema": SNAPSHOT_SCHEMA,
        "company_id": company,
        "captured_at": _iso(captured_at or _now()),
        "configured": bool(payload.get("configured")),
        "items": items,
        "summary": {
            "attention_candidates": len(items),
            "facebook_messages": sum(row["kind"] == "facebook_message" for row in items),
            "instagram_comments": sum(row["kind"] == "instagram_comment" for row in items),
            "skipped_unknown_time_or_identity": skipped,
        },
        "contracts": {
            "source_refresh": "EXPLICIT_OPERATOR",
            "provider_read_happened_before_snapshot": True,
            "latest_facebook_message_only": True,
            "secret_free": True,
            "provider_links_persisted": False,
            "person_ids_persisted": False,
            "full_message_bodies_persisted": False,
        },
    }


class InboxAttentionStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, company_id: str) -> Path:
        company = str(company_id or "").strip()
        if not COMPANY_ID_RE.fullmatch(company):
            raise ValueError("invalid company id")
        return self.root / f"{company}.json"

    def save(self, snapshot: dict) -> dict:
        if not isinstance(snapshot, dict) or snapshot.get("schema") != SNAPSHOT_SCHEMA:
            raise ValueError("invalid inbox attention snapshot")
        company = str(snapshot.get("company_id") or "").strip()
        write_json_atomic(self._path(company), snapshot)
        return deepcopy(snapshot)

    def capture(self, company_id: str, *, page_id: str | None, instagram_id: str | None, payload: dict) -> dict:
        return self.save(build_snapshot(company_id, page_id=page_id, instagram_id=instagram_id, payload=payload))

    def get(self, company_id: str) -> dict | None:
        path = self._path(company_id)
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or payload.get("schema") != SNAPSHOT_SCHEMA
            or payload.get("company_id") != company_id
            or not isinstance(payload.get("items"), list)
            or _parse(payload.get("captured_at")) is None
        ):
            raise ValueError("invalid inbox attention snapshot")
        return payload


def reply_stages(reply_root: Path, company_id: str) -> dict[tuple[str, str], str]:
    """Invalid/corrupt checkpoints never suppress an interaction as already answered."""
    stages: dict[tuple[str, str], str] = {}
    for path in Path(reply_root).glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or payload.get("company_id") != company_id:
            continue
        kind = str(payload.get("kind") or "").strip()
        interaction_id = str(payload.get("interaction_id") or "").strip()
        stage = str(payload.get("stage") or "").strip().upper()
        if kind not in {"facebook_message", "instagram_comment"} or not interaction_id or stage not in _STAGE_ORDER:
            continue
        key = (kind, interaction_id)
        existing = stages.get(key)
        if existing is None or _STAGE_ORDER[stage] > _STAGE_ORDER[existing]:
            stages[key] = stage
    return stages


def _marker(kind: str, interaction_id: str) -> str:
    label = "MESSAGE" if kind == "facebook_message" else "COMMENT"
    return f"[MKTGAPP_META_{label}:{interaction_id}]"


def project_attention(
    snapshot: dict | None,
    *,
    activities: Iterable[object],
    stages: dict[tuple[str, str], str],
    now: datetime | None = None,
) -> dict:
    current = now or _now()
    summaries = [str(getattr(row, "summary", "") or "") for row in activities]
    if snapshot is None:
        return _projection("MISSING", None, [], True, 0, 0)

    captured = _parse(snapshot.get("captured_at"))
    if captured is None:
        raise ValueError("invalid inbox attention captured_at")
    age = current - captured
    if age.total_seconds() < -300:
        return _projection("FUTURE_ANOMALY", snapshot.get("captured_at"), [], True, 0, 0)
    if age > STALE_AFTER:
        return _projection("STALE", snapshot.get("captured_at"), [], True, 0, 0)

    rows: list[dict] = []
    suppressed_crm = 0
    suppressed_reply = 0
    for item in snapshot.get("items") or []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        interaction_id = str(item.get("interaction_id") or "")
        if kind not in {"facebook_message", "instagram_comment"} or not interaction_id:
            continue
        if any(_marker(kind, interaction_id) in summary for summary in summaries):
            suppressed_crm += 1
            continue
        stage = stages.get((kind, interaction_id))
        if stage == "SENT":
            suppressed_reply += 1
            continue

        actor = f"@{item['actor_handle']}" if item.get("actor_handle") else "Interacción social"
        if stage in {"SENDING", "AMBIGUOUS"}:
            rows.append({
                **item,
                "attention_kind": "reply_verification",
                "rank": 18,
                "urgency": "HIGH",
                "blocking": True,
                "title": f"Verificar respuesta antes de reenviar · {actor}",
                "detail": "Existe un intento de respuesta sin confirmación durable; actualiza la bandeja y verifica Meta antes de cualquier nuevo envío.",
                "reason_code": f"INBOX_REPLY_{stage}",
            })
            continue
        if kind == "facebook_message" and item.get("reply_eligible"):
            rank, urgency, attention_kind = 27, "HIGH", "incoming_message"
            title = f"Responder mensaje reciente · {actor}"
        elif kind == "facebook_message":
            rank, urgency, attention_kind = 47, "MEDIUM", "message_triage"
            title = f"Revisar mensaje social · {actor}"
        else:
            rank, urgency, attention_kind = 45, "MEDIUM", "instagram_comment"
            title = f"Atender comentario de Instagram · {actor}"
        rows.append({
            **item,
            "attention_kind": attention_kind,
            "rank": rank,
            "urgency": urgency,
            "blocking": False,
            "title": title,
            "detail": item.get("excerpt") or "Interacción capturada en la última actualización explícita de la bandeja.",
            "reason_code": "INBOX_EXPLICIT_REFRESH_ATTENTION",
        })

    rows.sort(key=lambda row: (row["rank"], row["occurred_at"], row["interaction_id"]))
    return _projection("CURRENT", snapshot.get("captured_at"), rows[:20], False, suppressed_crm, suppressed_reply)


def _projection(state: str, captured_at: object, items: list[dict], refresh: bool, crm: int, reply: int) -> dict:
    return {
        "schema": ATTENTION_SCHEMA,
        "snapshot_state": state,
        "captured_at": captured_at,
        "items": items,
        "refresh_required": refresh,
        "suppressed_by_crm": crm,
        "suppressed_by_reply": reply,
        "provider_read_performed": False,
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


def extend_action_center(payload: dict, attention: dict) -> dict:
    """Extend, never replace, the existing Action Center priority queue."""
    result = deepcopy(payload)
    queue = list(result.get("queue") or [])
    for row in attention.get("items") or []:
        queue.append(action_base._item(
            rank=int(row["rank"]),
            urgency=str(row["urgency"]),
            source="INBOX",
            kind=str(row["attention_kind"]),
            title=str(row["title"]),
            detail=str(row["detail"]),
            action_label="Abrir bandeja",
            view="inbox",
            tab=str(row.get("kind") or ""),
            entity_id=str(row.get("interaction_id") or ""),
            contact_id=row.get("crm_contact_id"),
            due_at=row.get("occurred_at"),
            blocking=bool(row.get("blocking")),
            reason_code=str(row["reason_code"]),
            reason="La interacción proviene del último refresh explícito de Meta; Action Center sólo usa la copia local minimizada y nunca consulta al proveedor.",
        ))
    if attention.get("refresh_required"):
        state = str(attention.get("snapshot_state") or "MISSING")
        queue.append(action_base._item(
            rank=76,
            urgency="LOW",
            source="INBOX",
            kind="inbox_refresh",
            title="Actualizar bandeja social",
            detail="No hay una lectura local reciente de Meta. Abre la bandeja y pulsa Actualizar para renovar la evidencia.",
            action_label="Abrir bandeja",
            view="inbox",
            reason_code=f"INBOX_SNAPSHOT_{state}",
            reason="La app no consulta Meta en segundo plano; la actualización sigue requiriendo una acción humana explícita.",
        ))

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
        "inbox_snapshot_state": attention.get("snapshot_state"),
        "inbox_attention": len(attention.get("items") or []),
    })
    result.setdefault("contracts", {})["inbox_attention_uses_explicit_local_snapshot"] = True
    result.setdefault("safety", {})["inbox_provider_read_performed"] = False
    result["inbox_attention"] = {
        "snapshot_state": attention.get("snapshot_state"),
        "captured_at": attention.get("captured_at"),
        "refresh_required": bool(attention.get("refresh_required")),
        "suppressed_by_crm": int(attention.get("suppressed_by_crm") or 0),
        "suppressed_by_reply": int(attention.get("suppressed_by_reply") or 0),
    }
    return result


__all__ = [
    "ATTENTION_SCHEMA",
    "InboxAttentionStore",
    "SNAPSHOT_SCHEMA",
    "build_snapshot",
    "extend_action_center",
    "project_attention",
    "reply_stages",
]
