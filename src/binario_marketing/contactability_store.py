from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .crm_store import CONTACT_ID_RE
from .social_store import _now


CONTACTABILITY_CHANNELS = ("email", "whatsapp")
CONTACTABILITY_STATUSES = ("UNKNOWN", "OPTED_IN", "OPTED_OUT")
SOURCE_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,160}$")


def _channel(value: object) -> str:
    channel = str(value or "").strip().lower()
    if channel not in CONTACTABILITY_CHANNELS:
        raise ValueError("unsupported contactability channel")
    return channel


def _status(value: object) -> str:
    status = str(value or "UNKNOWN").strip().upper()
    if status not in CONTACTABILITY_STATUSES:
        raise ValueError("unsupported contactability status")
    return status


def _text(value: object, limit: int, *, field: str) -> str | None:
    result = str(value or "").strip()
    if len(result) > limit:
        raise ValueError(f"{field} is too long")
    return result or None


def _captured_at(value: object) -> str | None:
    if value in (None, ""):
        return None
    raw = str(value).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("captured_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("captured_at must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _company_id(value: object) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def _contact_id(value: object) -> str:
    contact_id = str(value or "").strip()
    if not CONTACT_ID_RE.fullmatch(contact_id):
        raise ValueError("invalid contact id")
    return contact_id


@dataclass(frozen=True)
class Contactability:
    company_id: str
    contact_id: str
    channel: str
    status: str
    source: str | None
    captured_at: str | None
    note: str | None
    created_at: str | None
    updated_at: str | None


class ContactabilityStore:
    """Current local channel-contactability state. Absence means UNKNOWN."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def default(company_id: str, contact_id: str, channel: str) -> Contactability:
        return Contactability(
            company_id=_company_id(company_id),
            contact_id=_contact_id(contact_id),
            channel=_channel(channel),
            status="UNKNOWN",
            source=None,
            captured_at=None,
            note=None,
            created_at=None,
            updated_at=None,
        )

    def _path(self, company_id: str, contact_id: str, channel: str) -> Path:
        company = _company_id(company_id)
        contact = _contact_id(contact_id)
        clean_channel = _channel(channel)
        company_root = self.root / company
        company_root.mkdir(parents=True, exist_ok=True)
        return company_root / f"{contact}--{clean_channel}.json"

    @staticmethod
    def _load(path: Path) -> Contactability:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid contactability payload")
        row = Contactability(**payload)
        _company_id(row.company_id)
        _contact_id(row.contact_id)
        _channel(row.channel)
        _status(row.status)
        return row

    def get(self, company_id: str, contact_id: str, channel: str) -> Contactability:
        path = self._path(company_id, contact_id, channel)
        with self._lock:
            if not path.is_file():
                return self.default(company_id, contact_id, channel)
            return self._load(path)

    def for_contact(self, company_id: str, contact_id: str) -> dict[str, Contactability]:
        return {
            channel: self.get(company_id, contact_id, channel)
            for channel in CONTACTABILITY_CHANNELS
        }

    def set(self, company_id: str, contact_id: str, channel: str, payload: dict) -> Contactability:
        if not isinstance(payload, dict):
            raise ValueError("contactability payload must be an object")
        unknown = set(payload) - {"status", "source", "captured_at", "note"}
        if unknown:
            raise ValueError(f"unsupported contactability fields: {', '.join(sorted(unknown))}")
        company = _company_id(company_id)
        contact = _contact_id(contact_id)
        clean_channel = _channel(channel)
        clean_status = _status(payload.get("status"))
        source = _text(payload.get("source"), 160, field="source")
        note = _text(payload.get("note"), 2000, field="note")
        captured = _captured_at(payload.get("captured_at"))
        if clean_status in {"OPTED_IN", "OPTED_OUT"} and not source:
            raise ValueError("source is required for explicit contactability decisions")
        if clean_status in {"OPTED_IN", "OPTED_OUT"} and not captured:
            raise ValueError("captured_at is required for explicit contactability decisions")
        path = self._path(company, contact, clean_channel)
        with self._lock:
            current = self._load(path) if path.is_file() else self.default(company, contact, clean_channel)
            now = _now()
            row = Contactability(
                company_id=company,
                contact_id=contact,
                channel=clean_channel,
                status=clean_status,
                source=source,
                captured_at=captured,
                note=note,
                created_at=current.created_at or now,
                updated_at=now,
            )
            write_json_atomic(path, asdict(row))
            return row

    def reset(self, company_id: str, contact_id: str, channel: str) -> Contactability:
        path = self._path(company_id, contact_id, channel)
        with self._lock:
            path.unlink(missing_ok=True)
        return self.default(company_id, contact_id, channel)

    def list(self, company_id: str | None = None) -> list[Contactability]:
        if company_id:
            company = _company_id(company_id)
            paths = (self.root / company).glob("contact_*--*.json") if (self.root / company).is_dir() else []
        else:
            paths = self.root.glob("company_*/contact_*--*.json")
        with self._lock:
            rows = [self._load(path) for path in paths]
        return sorted(rows, key=lambda row: (row.company_id, row.contact_id, row.channel))

    def summary(self, company_id: str | None = None) -> dict:
        rows = self.list(company_id)
        counts = {
            channel: {status: 0 for status in CONTACTABILITY_STATUSES}
            for channel in CONTACTABILITY_CHANNELS
        }
        for row in rows:
            counts[row.channel][row.status] += 1
        return {"records": len(rows), "channels": counts}


__all__ = [
    "CONTACTABILITY_CHANNELS",
    "CONTACTABILITY_STATUSES",
    "Contactability",
    "ContactabilityStore",
]
