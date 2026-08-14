from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now, _parse_when


CAMPAIGN_ID_RE = re.compile(r"^campaign_[0-9a-f]{24}$")
CONTACT_ID_RE = re.compile(r"^contact_[0-9a-f]{24}$")
MEDIA_ID_RE = re.compile(r"^media_[0-9a-f]{24}$")
PUBLICATION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
CAMPAIGN_STATUSES = ("PLANNING", "READY", "IN_PROGRESS", "COMPLETED", "ARCHIVED")
CAMPAIGN_OBJECTIVES = ("AWARENESS", "ENGAGEMENT", "LEADS", "SALES", "RETENTION", "OTHER")
CAMPAIGN_CHANNELS = ("facebook_page", "instagram", "email", "whatsapp")


def _text(value: object, limit: int, *, required: bool = False, field: str = "value") -> str | None:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > limit:
        raise ValueError(f"{field} is too long")
    return result or None


def _enum(value: object, allowed: tuple[str, ...], *, field: str, default: str) -> str:
    result = str(value or default).strip().upper()
    if result not in allowed:
        raise ValueError(f"unsupported {field}")
    return result


def _when(value: object) -> str | None:
    if value in (None, ""):
        return None
    parsed = _parse_when(str(value))
    return parsed.isoformat() if parsed else None


def _ids(value: object, pattern: re.Pattern[str], *, field: str, limit: int = 5000) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field} must be an array")
    result: list[str] = []
    for raw in value:
        item = str(raw or "").strip()
        if not item:
            continue
        if not pattern.fullmatch(item):
            raise ValueError(f"invalid {field} item")
        if item not in result:
            result.append(item)
    if len(result) > limit:
        raise ValueError(f"too many {field}")
    return tuple(result)


def _channels(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("channels must be an array")
    result: list[str] = []
    for raw in value:
        channel = str(raw or "").strip().lower()
        if not channel:
            continue
        if channel not in CAMPAIGN_CHANNELS:
            raise ValueError("unsupported campaign channel")
        if channel not in result:
            result.append(channel)
    return tuple(result)


def _date_order(start_at: str | None, end_at: str | None) -> None:
    if not start_at or not end_at:
        return
    start = datetime.fromisoformat(start_at.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_at.replace("Z", "+00:00"))
    if end < start:
        raise ValueError("campaign end date cannot be before start date")


@dataclass(frozen=True)
class Campaign:
    id: str
    company_id: str
    name: str
    objective: str
    status: str
    start_at: str | None
    end_at: str | None
    channels: tuple[str, ...]
    audience_contact_ids: tuple[str, ...]
    media_ids: tuple[str, ...]
    publication_ids: tuple[str, ...]
    notes: str | None
    created_at: str
    updated_at: str


class CampaignStore:
    """Durable campaign planning state. It never sends, publishes or activates providers."""

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
    def _campaign_id(value: str) -> str:
        campaign_id = str(value or "").strip()
        if not CAMPAIGN_ID_RE.fullmatch(campaign_id):
            raise ValueError("invalid campaign id")
        return campaign_id

    def _path(self, campaign_id: str) -> Path:
        return self.root / f"{self._campaign_id(campaign_id)}.json"

    @staticmethod
    def _load(path: Path) -> Campaign:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid campaign payload")
        for field in ("channels", "audience_contact_ids", "media_ids", "publication_ids"):
            payload[field] = tuple(payload.get(field) or ())
        return Campaign(**payload)

    @staticmethod
    def _values(company_id: str, payload: dict, current: Campaign | None = None) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("campaign payload must be an object")
        allowed = {
            "name", "objective", "status", "start_at", "end_at", "channels",
            "audience_contact_ids", "media_ids", "publication_ids", "notes",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported campaign fields: {', '.join(sorted(unknown))}")
        base = asdict(current) if current else {}
        name = _text(payload.get("name", base.get("name")), 180, required=True, field="campaign name") or ""
        objective = _enum(payload.get("objective", base.get("objective")), CAMPAIGN_OBJECTIVES, field="campaign objective", default="OTHER")
        status = _enum(payload.get("status", base.get("status")), CAMPAIGN_STATUSES, field="campaign status", default="PLANNING")
        start_at = _when(payload.get("start_at", base.get("start_at")))
        end_at = _when(payload.get("end_at", base.get("end_at")))
        _date_order(start_at, end_at)
        channels = _channels(payload.get("channels", base.get("channels", ())))
        audience = _ids(payload.get("audience_contact_ids", base.get("audience_contact_ids", ())), CONTACT_ID_RE, field="audience_contact_ids")
        media = _ids(payload.get("media_ids", base.get("media_ids", ())), MEDIA_ID_RE, field="media_ids")
        publications = _ids(payload.get("publication_ids", base.get("publication_ids", ())), PUBLICATION_ID_RE, field="publication_ids")
        notes = _text(payload.get("notes", base.get("notes")), 10000)
        return {
            "company_id": company_id,
            "name": name,
            "objective": objective,
            "status": status,
            "start_at": start_at,
            "end_at": end_at,
            "channels": channels,
            "audience_contact_ids": audience,
            "media_ids": media,
            "publication_ids": publications,
            "notes": notes,
        }

    def create(self, company_id: str, payload: dict) -> Campaign:
        company = self._company_id(company_id)
        values = self._values(company, payload)
        now = _now()
        row = Campaign(
            id=f"campaign_{uuid.uuid4().hex[:24]}",
            **values,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._path(row.id), asdict(row))
        return row

    def get(self, campaign_id: str) -> Campaign:
        with self._lock:
            path = self._path(campaign_id)
            if not path.is_file():
                raise KeyError(campaign_id)
            return self._load(path)

    def get_for_company(self, company_id: str, campaign_id: str) -> Campaign:
        company = self._company_id(company_id)
        row = self.get(campaign_id)
        if row.company_id != company:
            raise KeyError(campaign_id)
        return row

    def list(self, company_id: str | None = None) -> list[Campaign]:
        company = self._company_id(company_id) if company_id else None
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("campaign_*.json")]
        if company:
            rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.start_at or row.created_at, row.id), reverse=True)

    def update(self, company_id: str, campaign_id: str, payload: dict) -> Campaign:
        company = self._company_id(company_id)
        with self._lock:
            current = self.get_for_company(company, campaign_id)
            values = self._values(company, payload, current)
            row = Campaign(
                id=current.id,
                **values,
                created_at=current.created_at,
                updated_at=_now(),
            )
            write_json_atomic(self._path(row.id), asdict(row))
            return row

    def summary(self, company_id: str | None = None) -> dict:
        rows = self.list(company_id)
        status_counts = {status: 0 for status in CAMPAIGN_STATUSES}
        for row in rows:
            status_counts[row.status] += 1
        return {
            "total": len(rows),
            "planning": status_counts["PLANNING"],
            "ready": status_counts["READY"],
            "in_progress": status_counts["IN_PROGRESS"],
            "completed": status_counts["COMPLETED"],
            "archived": status_counts["ARCHIVED"],
            "status_counts": status_counts,
        }


__all__ = [
    "CAMPAIGN_CHANNELS",
    "CAMPAIGN_ID_RE",
    "CAMPAIGN_OBJECTIVES",
    "CAMPAIGN_STATUSES",
    "Campaign",
    "CampaignStore",
]
