from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .atomic import write_json_atomic
from .attribution_store import (
    CONTACT_ID_RE,
    OPPORTUNITY_ID_RE,
    TRACKING_CODE_RE,
    TRACKING_LINK_ID_RE,
    _utm,
)
from .company_store import COMPANY_ID_RE
from .social_store import _assert_secret_free, _now


LEAD_INTAKE_SCHEMA = "binario.marketing.lead-intake.v1"
LEAD_ID_RE = re.compile(r"^lead_[0-9a-f]{24}$")
LEAD_CONNECTORS = ("FIRST_PARTY_FORM", "CSV_IMPORT", "API_IMPORT", "MANUAL")
CONVERSION_BASES = ("CREATED_NEW_CONTACT", "EXACT_IDENTITY_MATCH", "USER_SELECTED_CONTACT")
MAX_LEAD_CSV_BYTES = 10 * 1024 * 1024
MAX_LEAD_CSV_ROWS = 10000

_CONTACT_FIELDS = (
    "name", "organization", "role", "email", "phone", "whatsapp",
    "instagram", "source", "tags", "notes",
)
_ATTRIBUTION_FIELDS = (
    "bm_tid", "utm_source", "utm_medium", "utm_campaign", "utm_id",
    "utm_content", "utm_term", "utm_source_platform",
)
_CSV_ALIASES = {
    "name": "name", "nombre": "name",
    "organization": "organization", "organizacion": "organization", "organización": "organization", "empresa": "organization",
    "role": "role", "cargo": "role",
    "email": "email", "correo": "email", "correo_electronico": "email", "correo_electrónico": "email",
    "phone": "phone", "telefono": "phone", "teléfono": "phone",
    "whatsapp": "whatsapp",
    "instagram": "instagram",
    "source": "source", "origen": "source",
    "tags": "tags", "etiquetas": "tags",
    "notes": "notes", "notas": "notes",
    "source_ref": "source_ref", "external_id": "source_ref", "id_externo": "source_ref",
    "bm_tid": "bm_tid",
    "utm_source": "utm_source",
    "utm_medium": "utm_medium",
    "utm_campaign": "utm_campaign",
    "utm_id": "utm_id",
    "utm_content": "utm_content",
    "utm_term": "utm_term",
    "utm_source_platform": "utm_source_platform",
}


def _company(value: object) -> str:
    text = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(text):
        raise ValueError("invalid company id")
    return text


def _lead_id(value: object) -> str:
    text = str(value or "").strip()
    if not LEAD_ID_RE.fullmatch(text):
        raise ValueError("invalid lead id")
    return text


def _optional_id(value: object, pattern: re.Pattern[str], field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not pattern.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def _text(value: object, limit: int, *, field: str) -> str | None:
    text = str(value or "").strip()
    if len(text) > limit:
        raise ValueError(f"{field} is too long")
    return text or None


def _tags(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        raw_items = re.split(r"[,;|]", value)
    elif isinstance(value, (list, tuple)):
        raw_items = value
    else:
        raise ValueError("tags must be an array or delimited string")
    result: list[str] = []
    for raw in raw_items:
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


def _timestamp(value: object, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        return _now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _connector(value: object) -> str:
    text = str(value or "").strip().upper()
    if text not in LEAD_CONNECTORS:
        raise ValueError(f"connector must be one of {', '.join(LEAD_CONNECTORS)}")
    return text


def _email(value: object) -> str | None:
    text = _text(value, 254, field="email")
    return text.casefold() if text else None


def _phone_key(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = re.sub(r"\D", "", text)
    return digits or None


def _instagram_key(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.lower().startswith(("http://", "https://")):
        parsed = urlsplit(text)
        host = (parsed.hostname or "").casefold()
        if host in {"instagram.com", "www.instagram.com"}:
            text = (parsed.path.strip("/").split("/", 1)[0] if parsed.path.strip("/") else "")
    text = text.lstrip("@").strip().casefold()
    if not re.fullmatch(r"[a-z0-9._]{1,60}", text):
        return None
    return text


def identity_keys(payload: object) -> tuple[tuple[str, str], ...]:
    get = payload.get if isinstance(payload, dict) else lambda key: getattr(payload, key, None)
    keys: set[tuple[str, str]] = set()
    email = _email(get("email"))
    if email:
        keys.add(("email", email))
    for field in ("phone", "whatsapp"):
        phone = _phone_key(get(field))
        if phone:
            keys.add(("phone", phone))
    instagram = _instagram_key(get("instagram"))
    if instagram:
        keys.add(("instagram", instagram))
    return tuple(sorted(keys))


def _fingerprint(values: dict) -> str:
    canonical = json.dumps(values, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LeadIntake:
    schema: str
    id: str
    company_id: str
    connector: str
    source_ref: str | None
    content_fingerprint: str
    name: str | None
    organization: str | None
    role: str | None
    email: str | None
    phone: str | None
    whatsapp: str | None
    instagram: str | None
    source: str | None
    tags: tuple[str, ...]
    notes: str | None
    tracking_link_id: str | None
    tracking_code: str | None
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    utm_id: str | None
    utm_content: str | None
    utm_term: str | None
    utm_source_platform: str | None
    received_at: str
    created_at: str
    converted_contact_id: str | None
    converted_opportunity_id: str | None
    conversion_basis: str | None
    converted_at: str | None
    dismissed_at: str | None
    dismissal_reason: str | None


class LeadIntakeStore:
    """Durable company-scoped lead inbox. Intake never mutates CRM by itself."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, lead_id: str) -> Path:
        return self.root / f"{_lead_id(lead_id)}.json"

    @staticmethod
    def _load(path: Path) -> LeadIntake:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid lead intake payload")
        _assert_secret_free(payload)
        payload["tags"] = tuple(payload.get("tags") or ())
        return LeadIntake(**payload)

    def create(self, company_id: str, payload: dict) -> LeadIntake:
        company = _company(company_id)
        if not isinstance(payload, dict):
            raise ValueError("lead intake payload must be an object")
        _assert_secret_free(payload)
        allowed = {
            "connector", "source_ref", *_CONTACT_FIELDS,
            "tracking_link_id", "tracking_code",
            "utm_source", "utm_medium", "utm_campaign", "utm_id",
            "utm_content", "utm_term", "utm_source_platform",
            "received_at",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported lead intake fields: {', '.join(sorted(unknown))}")
        connector = _connector(payload.get("connector"))
        source_ref = _text(payload.get("source_ref"), 200, field="source_ref")
        values = {
            "name": _text(payload.get("name"), 160, field="name"),
            "organization": _text(payload.get("organization"), 160, field="organization"),
            "role": _text(payload.get("role"), 120, field="role"),
            "email": _text(payload.get("email"), 254, field="email"),
            "phone": _text(payload.get("phone"), 80, field="phone"),
            "whatsapp": _text(payload.get("whatsapp"), 80, field="whatsapp"),
            "instagram": _text(payload.get("instagram"), 120, field="instagram"),
            "source": _text(payload.get("source"), 120, field="source"),
            "tags": _tags(payload.get("tags")),
            "notes": _text(payload.get("notes"), 5000, field="notes"),
        }
        if not values["name"] and not identity_keys(values):
            raise ValueError("lead requires a name or at least one exact identity field")
        tracking_link_id = _optional_id(payload.get("tracking_link_id"), TRACKING_LINK_ID_RE, "tracking_link_id")
        tracking_code = _optional_id(payload.get("tracking_code"), TRACKING_CODE_RE, "tracking_code")
        if bool(tracking_link_id) != bool(tracking_code):
            raise ValueError("tracking_link_id and tracking_code must be supplied together")
        attribution = {
            "tracking_link_id": tracking_link_id,
            "tracking_code": tracking_code,
            "utm_source": _utm(payload.get("utm_source"), field="utm_source") if tracking_link_id else None,
            "utm_medium": _utm(payload.get("utm_medium"), field="utm_medium") if tracking_link_id else None,
            "utm_campaign": _utm(payload.get("utm_campaign"), field="utm_campaign") if tracking_link_id else None,
            "utm_id": _utm(payload.get("utm_id"), field="utm_id") if tracking_link_id else None,
            "utm_content": _utm(payload.get("utm_content"), field="utm_content") if tracking_link_id else None,
            "utm_term": _utm(payload.get("utm_term"), field="utm_term") if tracking_link_id else None,
            "utm_source_platform": _utm(payload.get("utm_source_platform"), field="utm_source_platform") if tracking_link_id else None,
        }
        if tracking_link_id and not all(attribution[key] for key in ("utm_source", "utm_medium", "utm_campaign", "utm_id")):
            raise ValueError("verified attribution requires canonical source, medium, campaign and utm_id")
        fingerprint_values = {
            "connector": connector,
            "source_ref": source_ref,
            **{key: (list(value) if isinstance(value, tuple) else value) for key, value in values.items()},
            **attribution,
        }
        fingerprint = _fingerprint(fingerprint_values)
        received_at = _timestamp(payload.get("received_at"), field="received_at")
        with self._lock:
            if source_ref:
                for current in self.list(company):
                    if current.connector == connector and current.source_ref == source_ref:
                        if current.content_fingerprint == fingerprint:
                            return current
                        raise ValueError("source_ref already exists with a different lead payload")
            now = _now()
            row = LeadIntake(
                schema=LEAD_INTAKE_SCHEMA,
                id=f"lead_{uuid.uuid4().hex[:24]}",
                company_id=company,
                connector=connector,
                source_ref=source_ref,
                content_fingerprint=fingerprint,
                **values,
                **attribution,
                received_at=received_at,
                created_at=now,
                converted_contact_id=None,
                converted_opportunity_id=None,
                conversion_basis=None,
                converted_at=None,
                dismissed_at=None,
                dismissal_reason=None,
            )
            write_json_atomic(self._path(row.id), asdict(row))
            return row

    def get(self, company_id: str, lead_id: str) -> LeadIntake:
        company = _company(company_id)
        with self._lock:
            path = self._path(lead_id)
            if not path.is_file():
                raise KeyError(lead_id)
            row = self._load(path)
        if row.company_id != company:
            raise KeyError(lead_id)
        return row

    def list(self, company_id: str) -> list[LeadIntake]:
        company = _company(company_id)
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("lead_*.json")]
        rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.received_at, row.created_at, row.id), reverse=True)

    def mark_contact_conversion(self, company_id: str, lead_id: str, contact_id: str, *, basis: str) -> LeadIntake:
        company = _company(company_id)
        contact = _optional_id(contact_id, CONTACT_ID_RE, "contact_id")
        if not contact:
            raise ValueError("contact_id is required")
        basis_value = str(basis or "").strip().upper()
        if basis_value not in CONVERSION_BASES:
            raise ValueError("invalid conversion basis")
        with self._lock:
            current = self.get(company, lead_id)
            if current.dismissed_at:
                raise ValueError("dismissed lead cannot be converted")
            if current.converted_contact_id:
                if current.converted_contact_id != contact:
                    raise ValueError("lead is already converted to another contact")
                return current
            row = replace(
                current,
                converted_contact_id=contact,
                conversion_basis=basis_value,
                converted_at=_now(),
            )
            write_json_atomic(self._path(row.id), asdict(row))
            return row

    def mark_opportunity_conversion(self, company_id: str, lead_id: str, opportunity_id: str) -> LeadIntake:
        company = _company(company_id)
        opportunity = _optional_id(opportunity_id, OPPORTUNITY_ID_RE, "opportunity_id")
        if not opportunity:
            raise ValueError("opportunity_id is required")
        with self._lock:
            current = self.get(company, lead_id)
            if not current.converted_contact_id:
                raise ValueError("lead must be linked to a CRM contact first")
            if current.dismissed_at:
                raise ValueError("dismissed lead cannot be converted")
            if current.converted_opportunity_id:
                if current.converted_opportunity_id != opportunity:
                    raise ValueError("lead is already linked to another opportunity")
                return current
            row = replace(current, converted_opportunity_id=opportunity, converted_at=_now())
            write_json_atomic(self._path(row.id), asdict(row))
            return row

    def dismiss(self, company_id: str, lead_id: str, reason: object) -> LeadIntake:
        company = _company(company_id)
        why = _text(reason, 500, field="dismissal_reason")
        if not why:
            raise ValueError("dismissal_reason is required")
        with self._lock:
            current = self.get(company, lead_id)
            if current.converted_contact_id:
                raise ValueError("converted lead cannot be dismissed")
            if current.dismissed_at:
                return current
            row = replace(current, dismissed_at=_now(), dismissal_reason=why)
            write_json_atomic(self._path(row.id), asdict(row))
            return row


def _header(value: object) -> str:
    return str(value or "").strip().casefold().replace(" ", "_")


def parse_lead_csv(content: bytes) -> tuple[list[tuple[int, dict]], list[dict]]:
    if not isinstance(content, (bytes, bytearray)):
        raise ValueError("CSV content must be bytes")
    if not content:
        raise ValueError("CSV file is empty")
    if len(content) > MAX_LEAD_CSV_BYTES:
        raise ValueError("CSV file exceeds 10 MiB limit")
    try:
        text = bytes(content).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must use UTF-8 encoding") from exc
    reader = csv.DictReader(io.StringIO(text, newline=""))
    if not reader.fieldnames:
        raise ValueError("CSV header is required")
    mapped: list[str] = []
    for raw in reader.fieldnames:
        field = _CSV_ALIASES.get(_header(raw))
        if not field:
            raise ValueError(f"unsupported CSV column: {raw}")
        if field in mapped:
            raise ValueError(f"duplicate CSV column for {field}")
        mapped.append(field)

    rows: list[tuple[int, dict]] = []
    errors: list[dict] = []
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > MAX_LEAD_CSV_ROWS:
            raise ValueError("CSV exceeds 10000 data rows")
        payload: dict = {}
        capture: dict = {}
        for source_name, field in zip(reader.fieldnames, mapped):
            value = str(raw_row.get(source_name) or "").strip()
            if not value:
                continue
            if field == "tags":
                payload[field] = list(_tags(value))
            elif field in _ATTRIBUTION_FIELDS:
                capture[field] = value
            else:
                payload[field] = value
        if capture:
            if not capture.get("bm_tid"):
                errors.append({"row": index, "error": "UTM attribution columns require bm_tid"})
                continue
            payload["attribution_capture"] = capture
        if not payload.get("name") and not identity_keys(payload):
            errors.append({"row": index, "error": "lead requires name or identity"})
            continue
        rows.append((index, payload))
    return rows, errors


__all__ = [
    "CONVERSION_BASES",
    "LEAD_CONNECTORS",
    "LEAD_ID_RE",
    "LEAD_INTAKE_SCHEMA",
    "LeadIntake",
    "LeadIntakeStore",
    "MAX_LEAD_CSV_BYTES",
    "MAX_LEAD_CSV_ROWS",
    "identity_keys",
    "parse_lead_csv",
]
