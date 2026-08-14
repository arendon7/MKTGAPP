from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now, _parse_when


CONTACT_ID_RE = re.compile(r"^contact_[0-9a-f]{24}$")
OPPORTUNITY_ID_RE = re.compile(r"^opportunity_[0-9a-f]{24}$")
ACTIVITY_ID_RE = re.compile(r"^activity_[0-9a-f]{24}$")
STAGES = ("NEW", "CONTACTED", "INTERESTED", "PROPOSAL", "WON", "LOST")
ACTIVITY_TYPES = ("NOTE", "CALL", "WHATSAPP", "EMAIL", "MEETING", "TASK")


def _text(value: object, limit: int, *, required: bool = False, field: str = "value") -> str | None:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > limit:
        raise ValueError(f"{field} is too long")
    return result or None


def _tags(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("tags must be an array")
    result: list[str] = []
    for raw in value:
        tag = str(raw or "").strip()
        if not tag:
            continue
        if len(tag) > 40:
            raise ValueError("tag is too long")
        if tag.casefold() not in {item.casefold() for item in result}:
            result.append(tag)
    if len(result) > 30:
        raise ValueError("too many tags")
    return tuple(result)


def _money(value: object) -> int | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise ValueError("value must be a non-negative integer")
    try:
        amount = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("value must be a non-negative integer") from exc
    if amount < 0 or amount > 10**15:
        raise ValueError("value is outside supported range")
    return amount


def _when(value: object) -> str | None:
    if value in (None, ""):
        return None
    parsed = _parse_when(str(value))
    return parsed.isoformat() if parsed else None


@dataclass(frozen=True)
class Contact:
    id: str
    company_id: str
    name: str
    organization: str | None
    role: str | None
    email: str | None
    phone: str | None
    whatsapp: str | None
    instagram: str | None
    source: str | None
    tags: tuple[str, ...]
    notes: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Opportunity:
    id: str
    company_id: str
    contact_id: str | None
    title: str
    stage: str
    value: int | None
    currency: str
    next_action: str | None
    next_action_at: str | None
    notes: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class Activity:
    id: str
    company_id: str
    contact_id: str | None
    opportunity_id: str | None
    kind: str
    summary: str
    due_at: str | None
    completed_at: str | None
    created_at: str
    updated_at: str


class CRMStore:
    """Small durable CRM: contacts, opportunities and follow-up activities per company."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.contacts_root = self.root / "contacts"
        self.opportunities_root = self.root / "opportunities"
        self.activities_root = self.root / "activities"
        for path in (self.contacts_root, self.opportunities_root, self.activities_root):
            path.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _company_id(value: str) -> str:
        company_id = str(value or "").strip()
        if not COMPANY_ID_RE.fullmatch(company_id):
            raise ValueError("invalid company id")
        return company_id

    @staticmethod
    def _path(root: Path, row_id: str, pattern: re.Pattern[str]) -> Path:
        value = str(row_id or "").strip()
        if not pattern.fullmatch(value):
            raise ValueError("invalid CRM record id")
        return root / f"{value}.json"

    @staticmethod
    def _load(path: Path, cls):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid CRM payload")
        if cls is Contact:
            payload["tags"] = tuple(payload.get("tags") or ())
        return cls(**payload)

    def create_contact(self, company_id: str, payload: dict) -> Contact:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("contact payload must be an object")
        now = _now()
        row = Contact(
            id=f"contact_{uuid.uuid4().hex[:24]}",
            company_id=company,
            name=_text(payload.get("name"), 160, required=True, field="contact name") or "",
            organization=_text(payload.get("organization"), 160),
            role=_text(payload.get("role"), 120),
            email=_text(payload.get("email"), 254),
            phone=_text(payload.get("phone"), 80),
            whatsapp=_text(payload.get("whatsapp"), 80),
            instagram=_text(payload.get("instagram"), 120),
            source=_text(payload.get("source"), 120),
            tags=_tags(payload.get("tags")),
            notes=_text(payload.get("notes"), 5000),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._path(self.contacts_root, row.id, CONTACT_ID_RE), asdict(row))
        return row

    def get_contact(self, contact_id: str) -> Contact:
        with self._lock:
            path = self._path(self.contacts_root, contact_id, CONTACT_ID_RE)
            if not path.is_file():
                raise KeyError(contact_id)
            return self._load(path, Contact)

    def list_contacts(self, company_id: str | None = None) -> list[Contact]:
        company = self._company_id(company_id) if company_id else None
        with self._lock:
            rows = [self._load(path, Contact) for path in self.contacts_root.glob("contact_*.json")]
        if company:
            rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.name.casefold(), row.id))

    def update_contact(self, company_id: str, contact_id: str, payload: dict) -> Contact:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("contact payload must be an object")
        allowed = {"name", "organization", "role", "email", "phone", "whatsapp", "instagram", "source", "tags", "notes"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported contact fields: {', '.join(sorted(unknown))}")
        with self._lock:
            current = self.get_contact(contact_id)
            if current.company_id != company:
                raise KeyError(contact_id)
            values = asdict(current)
            if "name" in payload:
                values["name"] = _text(payload["name"], 160, required=True, field="contact name")
            for field, limit in (("organization", 160), ("role", 120), ("email", 254), ("phone", 80), ("whatsapp", 80), ("instagram", 120), ("source", 120), ("notes", 5000)):
                if field in payload:
                    values[field] = _text(payload[field], limit)
            if "tags" in payload:
                values["tags"] = _tags(payload["tags"])
            values["updated_at"] = _now()
            row = Contact(**values)
            write_json_atomic(self._path(self.contacts_root, row.id, CONTACT_ID_RE), asdict(row))
            return row

    def _validate_contact_reference(self, company_id: str, contact_id: str | None) -> str | None:
        if not contact_id:
            return None
        row = self.get_contact(contact_id)
        if row.company_id != company_id:
            raise ValueError("contact does not belong to this company")
        return row.id

    def create_opportunity(self, company_id: str, payload: dict) -> Opportunity:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("opportunity payload must be an object")
        contact_id = self._validate_contact_reference(company, _text(payload.get("contact_id"), 64))
        stage = str(payload.get("stage") or "NEW").strip().upper()
        if stage not in STAGES:
            raise ValueError("invalid opportunity stage")
        currency = str(payload.get("currency") or "COP").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("currency must be a 3-letter code")
        now = _now()
        row = Opportunity(
            id=f"opportunity_{uuid.uuid4().hex[:24]}",
            company_id=company,
            contact_id=contact_id,
            title=_text(payload.get("title"), 200, required=True, field="opportunity title") or "",
            stage=stage,
            value=_money(payload.get("value")),
            currency=currency,
            next_action=_text(payload.get("next_action"), 500),
            next_action_at=_when(payload.get("next_action_at")),
            notes=_text(payload.get("notes"), 5000),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._path(self.opportunities_root, row.id, OPPORTUNITY_ID_RE), asdict(row))
        return row

    def get_opportunity(self, opportunity_id: str) -> Opportunity:
        with self._lock:
            path = self._path(self.opportunities_root, opportunity_id, OPPORTUNITY_ID_RE)
            if not path.is_file():
                raise KeyError(opportunity_id)
            return self._load(path, Opportunity)

    def list_opportunities(self, company_id: str | None = None) -> list[Opportunity]:
        company = self._company_id(company_id) if company_id else None
        with self._lock:
            rows = [self._load(path, Opportunity) for path in self.opportunities_root.glob("opportunity_*.json")]
        if company:
            rows = [row for row in rows if row.company_id == company]
        order = {stage: index for index, stage in enumerate(STAGES)}
        return sorted(rows, key=lambda row: (order[row.stage], row.updated_at, row.id))

    def update_opportunity(self, company_id: str, opportunity_id: str, payload: dict) -> Opportunity:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("opportunity payload must be an object")
        allowed = {"contact_id", "title", "stage", "value", "currency", "next_action", "next_action_at", "notes"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported opportunity fields: {', '.join(sorted(unknown))}")
        with self._lock:
            current = self.get_opportunity(opportunity_id)
            if current.company_id != company:
                raise KeyError(opportunity_id)
            values = asdict(current)
            if "contact_id" in payload:
                values["contact_id"] = self._validate_contact_reference(company, _text(payload["contact_id"], 64))
            if "title" in payload:
                values["title"] = _text(payload["title"], 200, required=True, field="opportunity title")
            if "stage" in payload:
                stage = str(payload["stage"] or "").strip().upper()
                if stage not in STAGES:
                    raise ValueError("invalid opportunity stage")
                values["stage"] = stage
            if "value" in payload:
                values["value"] = _money(payload["value"])
            if "currency" in payload:
                currency = str(payload["currency"] or "").strip().upper()
                if not re.fullmatch(r"[A-Z]{3}", currency):
                    raise ValueError("currency must be a 3-letter code")
                values["currency"] = currency
            if "next_action" in payload:
                values["next_action"] = _text(payload["next_action"], 500)
            if "next_action_at" in payload:
                values["next_action_at"] = _when(payload["next_action_at"])
            if "notes" in payload:
                values["notes"] = _text(payload["notes"], 5000)
            values["updated_at"] = _now()
            row = Opportunity(**values)
            write_json_atomic(self._path(self.opportunities_root, row.id, OPPORTUNITY_ID_RE), asdict(row))
            return row

    def _validate_opportunity_reference(self, company_id: str, opportunity_id: str | None) -> str | None:
        if not opportunity_id:
            return None
        row = self.get_opportunity(opportunity_id)
        if row.company_id != company_id:
            raise ValueError("opportunity does not belong to this company")
        return row.id

    def create_activity(self, company_id: str, payload: dict) -> Activity:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("activity payload must be an object")
        contact_id = self._validate_contact_reference(company, _text(payload.get("contact_id"), 64))
        opportunity_id = self._validate_opportunity_reference(company, _text(payload.get("opportunity_id"), 80))
        if not contact_id and not opportunity_id:
            raise ValueError("activity requires a contact or opportunity")
        kind = str(payload.get("kind") or "NOTE").strip().upper()
        if kind not in ACTIVITY_TYPES:
            raise ValueError("invalid activity kind")
        now = _now()
        row = Activity(
            id=f"activity_{uuid.uuid4().hex[:24]}",
            company_id=company,
            contact_id=contact_id,
            opportunity_id=opportunity_id,
            kind=kind,
            summary=_text(payload.get("summary"), 2000, required=True, field="activity summary") or "",
            due_at=_when(payload.get("due_at")),
            completed_at=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._path(self.activities_root, row.id, ACTIVITY_ID_RE), asdict(row))
        return row

    def get_activity(self, activity_id: str) -> Activity:
        with self._lock:
            path = self._path(self.activities_root, activity_id, ACTIVITY_ID_RE)
            if not path.is_file():
                raise KeyError(activity_id)
            return self._load(path, Activity)

    def list_activities(self, company_id: str | None = None, *, contact_id: str | None = None, opportunity_id: str | None = None) -> list[Activity]:
        company = self._company_id(company_id) if company_id else None
        with self._lock:
            rows = [self._load(path, Activity) for path in self.activities_root.glob("activity_*.json")]
        if company:
            rows = [row for row in rows if row.company_id == company]
        if contact_id:
            rows = [row for row in rows if row.contact_id == contact_id]
        if opportunity_id:
            rows = [row for row in rows if row.opportunity_id == opportunity_id]
        return sorted(rows, key=lambda row: (row.due_at or row.created_at, row.created_at, row.id))

    def complete_activity(self, company_id: str, activity_id: str) -> Activity:
        company = self._company_id(company_id)
        with self._lock:
            current = self.get_activity(activity_id)
            if current.company_id != company:
                raise KeyError(activity_id)
            if current.completed_at:
                return current
            now = _now()
            row = replace(current, completed_at=now, updated_at=now)
            write_json_atomic(self._path(self.activities_root, row.id, ACTIVITY_ID_RE), asdict(row))
            return row

    def contact_detail(self, company_id: str, contact_id: str) -> dict:
        company = self._company_id(company_id)
        contact = self.get_contact(contact_id)
        if contact.company_id != company:
            raise KeyError(contact_id)
        opportunities = [row for row in self.list_opportunities(company) if row.contact_id == contact.id]
        activities = self.list_activities(company, contact_id=contact.id)
        return {
            "contact": asdict(contact),
            "opportunities": [asdict(row) for row in opportunities],
            "activities": [asdict(row) for row in activities],
        }

    def summary(self, company_id: str | None = None) -> dict:
        contacts = self.list_contacts(company_id)
        opportunities = self.list_opportunities(company_id)
        activities = self.list_activities(company_id)
        open_stages = {"NEW", "CONTACTED", "INTERESTED", "PROPOSAL"}
        open_opportunities = [row for row in opportunities if row.stage in open_stages]
        pending = [row for row in activities if row.completed_at is None]
        now = _parse_when(_now())
        overdue = [row for row in pending if row.due_at and _parse_when(row.due_at) < now]
        due = sorted((row for row in pending if row.due_at), key=lambda row: row.due_at or "")
        stage_counts = {stage: 0 for stage in STAGES}
        for row in opportunities:
            stage_counts[row.stage] += 1
        return {
            "contacts": len(contacts),
            "opportunities_open": len(open_opportunities),
            "opportunities_won": stage_counts["WON"],
            "pending_activities": len(pending),
            "overdue_activities": len(overdue),
            "stage_counts": stage_counts,
            "next_activities": [asdict(row) for row in due[:8]],
        }


__all__ = [
    "ACTIVITY_TYPES",
    "STAGES",
    "Activity",
    "Contact",
    "CRMStore",
    "Opportunity",
]
