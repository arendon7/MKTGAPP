from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
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


FIRST_PARTY_CAPTURE_SCHEMA = "binario.marketing.first-party-capture.v1"
CAPTURE_ID_RE = re.compile(r"^capture_[0-9a-f]{24}$")
CAPTURE_SOURCES = {
    "CRM_CONTACT_CREATE",
    "CRM_CONTACT_UPDATE",
    "CRM_OPPORTUNITY_CREATE",
    "CRM_OPPORTUNITY_UPDATE",
    "API_IMPORT",
}
BRIDGE_VERSION_RE = re.compile(r"^[A-Za-z0-9._-]{1,40}$")


def _company(value: object) -> str:
    text = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(text):
        raise ValueError("invalid company id")
    return text


def _record_id(value: object) -> str:
    text = str(value or "").strip()
    if not CAPTURE_ID_RE.fullmatch(text):
        raise ValueError("invalid capture id")
    return text


def _optional_id(value: object, pattern: re.Pattern[str], field: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if not pattern.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def _client_timestamp(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("client_captured_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("client_captured_at must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


def _host_only(value: object, *, field: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) > 3000:
        raise ValueError(f"{field} is too long")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{field} must not contain embedded credentials")
    host = parsed.hostname.lower().rstrip(".")
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return host[:255]


@dataclass(frozen=True)
class FirstPartyCapture:
    schema: str
    id: str
    company_id: str
    tracking_link_id: str
    tracking_code: str
    contact_id: str | None
    opportunity_id: str | None
    source: str
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_id: str
    utm_content: str | None
    utm_term: str | None
    utm_source_platform: str | None
    utm_validation: str
    landing_host: str | None
    referrer_host: str | None
    bridge_version: str | None
    client_captured_at: str | None
    received_at: str
    created_at: str


class FirstPartyCaptureStore:
    """Durable, PII-minimized evidence that a first-party form/CRM payload carried bm_tid.

    The store intentionally persists no contact name, email, phone, form body, landing query
    string or full referrer. Only CRM ids, canonical campaign parameters and host names survive.
    Server receive time is authoritative for attribution ordering; browser timestamps are metadata.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, capture_id: str) -> Path:
        return self.root / f"{_record_id(capture_id)}.json"

    @staticmethod
    def _load(path: Path) -> FirstPartyCapture:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid first-party capture payload")
        _assert_secret_free(payload)
        return FirstPartyCapture(**payload)

    def create(self, company_id: str, payload: dict) -> FirstPartyCapture:
        company = _company(company_id)
        if not isinstance(payload, dict):
            raise ValueError("capture payload must be an object")
        _assert_secret_free(payload)
        allowed = {
            "tracking_link_id", "tracking_code", "contact_id", "opportunity_id", "source",
            "utm_source", "utm_medium", "utm_campaign", "utm_id", "utm_content", "utm_term",
            "utm_source_platform", "landing_url", "referrer_url", "bridge_version",
            "client_captured_at", "received_at",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported capture fields: {', '.join(sorted(unknown))}")
        link_id = _optional_id(payload.get("tracking_link_id"), TRACKING_LINK_ID_RE, "tracking_link_id")
        if not link_id:
            raise ValueError("tracking_link_id is required")
        code = _optional_id(payload.get("tracking_code"), TRACKING_CODE_RE, "tracking_code")
        if not code:
            raise ValueError("tracking_code is required")
        contact_id = _optional_id(payload.get("contact_id"), CONTACT_ID_RE, "contact_id")
        opportunity_id = _optional_id(payload.get("opportunity_id"), OPPORTUNITY_ID_RE, "opportunity_id")
        if not contact_id and not opportunity_id:
            raise ValueError("capture requires a contact_id or opportunity_id")
        source = str(payload.get("source") or "").strip().upper()
        if source not in CAPTURE_SOURCES:
            raise ValueError("unsupported capture source")
        bridge_version = str(payload.get("bridge_version") or "").strip() or None
        if bridge_version and not BRIDGE_VERSION_RE.fullmatch(bridge_version):
            raise ValueError("invalid bridge_version")
        received_at = str(payload.get("received_at") or _now()).strip()
        try:
            received = datetime.fromisoformat(received_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("received_at must be an ISO timestamp") from exc
        if received.tzinfo is None:
            raise ValueError("received_at must include timezone")
        received_at = received.astimezone(timezone.utc).isoformat()
        values = {
            "utm_source": _utm(payload.get("utm_source"), field="utm_source", required=True) or "",
            "utm_medium": _utm(payload.get("utm_medium"), field="utm_medium", required=True) or "",
            "utm_campaign": _utm(payload.get("utm_campaign"), field="utm_campaign", required=True) or "",
            "utm_id": _utm(payload.get("utm_id"), field="utm_id", required=True) or "",
            "utm_content": _utm(payload.get("utm_content"), field="utm_content"),
            "utm_term": _utm(payload.get("utm_term"), field="utm_term"),
            "utm_source_platform": _utm(payload.get("utm_source_platform"), field="utm_source_platform"),
        }
        with self._lock:
            for current in self.list(company):
                if (
                    current.tracking_link_id == link_id
                    and current.contact_id == contact_id
                    and current.opportunity_id == opportunity_id
                    and current.source == source
                ):
                    return current
            now = _now()
            row = FirstPartyCapture(
                schema=FIRST_PARTY_CAPTURE_SCHEMA,
                id=f"capture_{uuid.uuid4().hex[:24]}",
                company_id=company,
                tracking_link_id=link_id,
                tracking_code=code,
                contact_id=contact_id,
                opportunity_id=opportunity_id,
                source=source,
                **values,
                utm_validation="MATCHED_CANONICAL_LINK",
                landing_host=_host_only(payload.get("landing_url"), field="landing_url"),
                referrer_host=_host_only(payload.get("referrer_url"), field="referrer_url"),
                bridge_version=bridge_version,
                client_captured_at=_client_timestamp(payload.get("client_captured_at")),
                received_at=received_at,
                created_at=now,
            )
            write_json_atomic(self._path(row.id), asdict(row))
            return row

    def get(self, company_id: str, capture_id: str) -> FirstPartyCapture:
        company = _company(company_id)
        with self._lock:
            path = self._path(capture_id)
            if not path.is_file():
                raise KeyError(capture_id)
            row = self._load(path)
        if row.company_id != company:
            raise KeyError(capture_id)
        return row

    def list(self, company_id: str) -> list[FirstPartyCapture]:
        company = _company(company_id)
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("capture_*.json")]
        rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.received_at, row.created_at, row.id), reverse=True)


__all__ = [
    "CAPTURE_ID_RE",
    "CAPTURE_SOURCES",
    "FIRST_PARTY_CAPTURE_SCHEMA",
    "FirstPartyCapture",
    "FirstPartyCaptureStore",
]
