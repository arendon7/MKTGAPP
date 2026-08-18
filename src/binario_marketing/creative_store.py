from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic import write_json_atomic
from .company_media_store import MEDIA_ID_RE
from .company_store import COMPANY_ID_RE
from .social_store import _now

CREATIVE_SCHEMA = "binario.marketing.creative-item.v1"
CAMPAIGN_ID_RE = re.compile(r"^campaign_[0-9a-f]{24}$")
REMOTE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CREATIVE_STAGES = ("BRIEF", "DRAFT", "READY", "SCHEDULED", "PUBLISHED", "PAID", "ARCHIVED")
CREATIVE_PURPOSES = ("AWARENESS", "ENGAGEMENT", "LEADS", "SALES", "RETENTION", "OTHER")
CREATIVE_CHANNELS = ("facebook_page", "instagram", "paid_media")
CTA_VALUES = ("LEARN_MORE", "SHOP_NOW", "SIGN_UP", "CONTACT_US", "GET_OFFER", "APPLY_NOW", "SUBSCRIBE", "NO_BUTTON")


def _text(value: Any, limit: int, *, field: str, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} is too long")
    return text or None


def _enum(value: Any, allowed: tuple[str, ...], *, field: str, default: str) -> str:
    result = str(value or default).strip().upper()
    if result not in allowed:
        raise ValueError(f"unsupported {field}")
    return result


def _channels(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("channels must be an array")
    result: list[str] = []
    for raw in value:
        channel = str(raw or "").strip().lower()
        if not channel:
            continue
        if channel not in CREATIVE_CHANNELS:
            raise ValueError("unsupported creative channel")
        if channel not in result:
            result.append(channel)
    return tuple(result)


def _ids(value: Any, *, field: str) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be an array")
    result: list[str] = []
    for raw in value:
        item = str(raw or "").strip()
        if not item:
            continue
        if not REMOTE_ID_RE.fullmatch(item):
            raise ValueError(f"invalid {field} item")
        if item not in result:
            result.append(item)
    return tuple(result)


def _timestamp(value: Any, field: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class CreativeItem:
    schema: str
    company_id: str
    media_id: str
    title: str
    stage: str
    purpose: str
    campaign_id: str | None
    channels: tuple[str, ...]
    primary_copy: str
    headline: str | None
    call_to_action: str
    destination_url: str | None
    public_media_url: str | None
    publish_at: str | None
    notes: str | None
    publication_ids: tuple[str, ...]
    paid_media_ids: tuple[str, ...]
    created_at: str
    updated_at: str


class CreativeStore:
    """Company-scoped creative workflow metadata around managed media.

    The store never owns media bytes and never sends or activates provider actions.
    It only connects a managed company asset to campaign/copy/channel workflow state.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _company_id(value: str) -> str:
        company_id = str(value or "").strip()
        if not COMPANY_ID_RE.fullmatch(company_id):
            raise ValueError("invalid company id")
        return company_id

    @staticmethod
    def _media_id(value: str) -> str:
        media_id = str(value or "").strip()
        if not MEDIA_ID_RE.fullmatch(media_id):
            raise ValueError("invalid company media id")
        return media_id

    def _path(self, company_id: str, media_id: str) -> Path:
        company = self._company_id(company_id)
        media = self._media_id(media_id)
        folder = self.root / company
        folder.mkdir(parents=True, exist_ok=True)
        return folder / f"{media}.json"

    @staticmethod
    def _load(path: Path) -> CreativeItem:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("schema") != CREATIVE_SCHEMA:
            raise ValueError("invalid creative item")
        for field in ("channels", "publication_ids", "paid_media_ids"):
            payload[field] = tuple(payload.get(field) or ())
        return CreativeItem(**payload)

    @staticmethod
    def _values(company_id: str, media_id: str, payload: dict, current: CreativeItem | None = None) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("creative payload must be an object")
        allowed = {
            "title", "stage", "purpose", "campaign_id", "channels", "primary_copy",
            "headline", "call_to_action", "destination_url", "public_media_url",
            "publish_at", "notes", "publication_ids", "paid_media_ids",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported creative fields: {', '.join(sorted(unknown))}")
        base = asdict(current) if current else {}
        title = _text(payload.get("title", base.get("title")), 180, field="creative title", required=True) or ""
        stage = _enum(payload.get("stage", base.get("stage")), CREATIVE_STAGES, field="creative stage", default="BRIEF")
        purpose = _enum(payload.get("purpose", base.get("purpose")), CREATIVE_PURPOSES, field="creative purpose", default="OTHER")
        campaign_id = str(payload.get("campaign_id", base.get("campaign_id")) or "").strip() or None
        if campaign_id and not CAMPAIGN_ID_RE.fullmatch(campaign_id):
            raise ValueError("invalid campaign id")
        channels = _channels(payload.get("channels", base.get("channels", ())))
        copy = _text(payload.get("primary_copy", base.get("primary_copy")), 20000, field="primary_copy") or ""
        headline = _text(payload.get("headline", base.get("headline")), 255, field="headline")
        cta = _enum(payload.get("call_to_action", base.get("call_to_action")), CTA_VALUES, field="call_to_action", default="LEARN_MORE")
        destination_url = _text(payload.get("destination_url", base.get("destination_url")), 2000, field="destination_url")
        public_media_url = _text(payload.get("public_media_url", base.get("public_media_url")), 2000, field="public_media_url")
        for field_name, url in (("destination_url", destination_url), ("public_media_url", public_media_url)):
            if url and not url.startswith("https://"):
                raise ValueError(f"{field_name} must use HTTPS")
        publish_at = _timestamp(payload.get("publish_at", base.get("publish_at")), "publish_at")
        notes = _text(payload.get("notes", base.get("notes")), 10000, field="notes")
        publications = _ids(payload.get("publication_ids", base.get("publication_ids", ())), field="publication_ids")
        paid = _ids(payload.get("paid_media_ids", base.get("paid_media_ids", ())), field="paid_media_ids")
        return {
            "schema": CREATIVE_SCHEMA,
            "company_id": company_id,
            "media_id": media_id,
            "title": title,
            "stage": stage,
            "purpose": purpose,
            "campaign_id": campaign_id,
            "channels": channels,
            "primary_copy": copy,
            "headline": headline,
            "call_to_action": cta,
            "destination_url": destination_url,
            "public_media_url": public_media_url,
            "publish_at": publish_at,
            "notes": notes,
            "publication_ids": publications,
            "paid_media_ids": paid,
        }

    def get(self, company_id: str, media_id: str) -> CreativeItem | None:
        with self._lock:
            path = self._path(company_id, media_id)
            return self._load(path) if path.is_file() else None

    def upsert(self, company_id: str, media_id: str, payload: dict) -> CreativeItem:
        company = self._company_id(company_id)
        media = self._media_id(media_id)
        with self._lock:
            current = self.get(company, media)
            values = self._values(company, media, payload, current)
            now = _now()
            row = CreativeItem(
                **values,
                created_at=current.created_at if current else now,
                updated_at=now,
            )
            write_json_atomic(self._path(company, media), asdict(row))
            return row

    def list(self, company_id: str) -> list[CreativeItem]:
        company = self._company_id(company_id)
        folder = self.root / company
        if not folder.is_dir():
            return []
        rows: list[CreativeItem] = []
        with self._lock:
            for path in folder.glob("media_*.json"):
                try:
                    rows.append(self._load(path))
                except (OSError, ValueError, json.JSONDecodeError, TypeError):
                    continue
        return sorted(rows, key=lambda row: (row.updated_at, row.media_id), reverse=True)

    def link_publication(self, company_id: str, media_id: str, publication_id: str, *, stage: str) -> CreativeItem:
        value = str(publication_id or "").strip()
        if not REMOTE_ID_RE.fullmatch(value):
            raise ValueError("invalid publication id")
        current = self.get(company_id, media_id)
        if current is None:
            raise KeyError(media_id)
        ids = list(current.publication_ids)
        if value not in ids:
            ids.append(value)
        return self.upsert(company_id, media_id, {"publication_ids": ids, "stage": stage})

    def link_paid_media(self, company_id: str, media_id: str, draft_id: str) -> CreativeItem:
        value = str(draft_id or "").strip()
        if not REMOTE_ID_RE.fullmatch(value):
            raise ValueError("invalid paid media draft id")
        current = self.get(company_id, media_id)
        if current is None:
            raise KeyError(media_id)
        ids = list(current.paid_media_ids)
        if value not in ids:
            ids.append(value)
        return self.upsert(company_id, media_id, {"paid_media_ids": ids, "stage": "PAID"})


__all__ = [
    "CREATIVE_CHANNELS",
    "CREATIVE_PURPOSES",
    "CREATIVE_SCHEMA",
    "CREATIVE_STAGES",
    "CreativeItem",
    "CreativeStore",
]
