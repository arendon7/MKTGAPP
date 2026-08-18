from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _assert_secret_free, _now


TRACKING_LINK_SCHEMA = "binario.marketing.tracking-link.v1"
ATTRIBUTION_CLAIM_SCHEMA = "binario.marketing.attribution-claim.v1"
TRACKING_LINK_ID_RE = re.compile(r"^tracking_[0-9a-f]{24}$")
ATTRIBUTION_CLAIM_ID_RE = re.compile(r"^attribution_[0-9a-f]{24}$")
CAMPAIGN_ID_RE = re.compile(r"^campaign_[0-9a-f]{24}$")
MEDIA_ID_RE = re.compile(r"^media_[0-9a-f]{24}$")
CONTACT_ID_RE = re.compile(r"^contact_[0-9a-f]{24}$")
OPPORTUNITY_ID_RE = re.compile(r"^opportunity_[0-9a-f]{24}$")
TRACKING_CODE_RE = re.compile(r"^bm_[0-9a-f]{24}$")
ATTRIBUTION_EVIDENCE = ("CAPTURED_TRACKING_CODE",)
_MANAGED_QUERY_KEYS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_id",
    "utm_content",
    "utm_term",
    "utm_source_platform",
    "bm_tid",
}
_SECRET_QUERY_KEYS = {"access_token", "token", "client_secret", "app_secret", "password", "authorization"}
_VALUE_RE = re.compile(r"^[A-Za-z0-9._~+-]{1,160}$")


def _company(value: object) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def _id(value: object, pattern: re.Pattern[str], *, field: str, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(f"{field} is required")
        return None
    if not pattern.fullmatch(text):
        raise ValueError(f"invalid {field}")
    return text


def _text(value: object, limit: int, *, field: str, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} is too long")
    return text or None


def _utm(value: object, *, field: str, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if not text:
        return None
    if not _VALUE_RE.fullmatch(text):
        raise ValueError(f"{field} must use letters, numbers, dot, dash, underscore, plus or tilde")
    return text


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


def _destination(value: object) -> str:
    raw = _text(value, 3000, field="destination_url", required=True) or ""
    parsed = urlsplit(raw)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("destination_url must be an absolute HTTPS URL")
    if parsed.username or parsed.password:
        raise ValueError("destination_url must not contain embedded credentials")
    for key, _ in parse_qsl(parsed.query, keep_blank_values=True):
        if key.strip().lower() in _SECRET_QUERY_KEYS:
            raise ValueError("destination_url must not contain credential-like query parameters")
    return raw


def build_tracked_url(
    destination_url: str,
    *,
    tracking_code: str,
    utm_source: str,
    utm_medium: str,
    utm_campaign: str,
    utm_id: str,
    utm_content: str | None = None,
    utm_term: str | None = None,
    utm_source_platform: str | None = None,
) -> str:
    destination = _destination(destination_url)
    code = _id(tracking_code, TRACKING_CODE_RE, field="tracking_code", required=True) or ""
    source = _utm(utm_source, field="utm_source", required=True) or ""
    medium = _utm(utm_medium, field="utm_medium", required=True) or ""
    campaign = _utm(utm_campaign, field="utm_campaign", required=True) or ""
    campaign_id = _utm(utm_id, field="utm_id", required=True) or ""
    content = _utm(utm_content, field="utm_content")
    term = _utm(utm_term, field="utm_term")
    platform = _utm(utm_source_platform, field="utm_source_platform")

    parsed = urlsplit(destination)
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True) if key.lower() not in _MANAGED_QUERY_KEYS]
    query.extend([
        ("utm_source", source),
        ("utm_medium", medium),
        ("utm_campaign", campaign),
        ("utm_id", campaign_id),
    ])
    if content:
        query.append(("utm_content", content))
    if term:
        query.append(("utm_term", term))
    if platform:
        query.append(("utm_source_platform", platform))
    query.append(("bm_tid", code))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment))


@dataclass(frozen=True)
class TrackingLink:
    schema: str
    id: str
    company_id: str
    campaign_id: str
    creative_media_id: str | None
    destination_url: str
    tracked_url: str
    tracking_code: str
    utm_source: str
    utm_medium: str
    utm_campaign: str
    utm_id: str
    utm_content: str | None
    utm_term: str | None
    utm_source_platform: str | None
    created_at: str


@dataclass(frozen=True)
class AttributionClaim:
    schema: str
    id: str
    company_id: str
    tracking_link_id: str
    tracking_code: str
    contact_id: str | None
    opportunity_id: str | None
    evidence: str
    captured_at: str
    created_at: str


class AttributionStore:
    """Durable first-party tracking instrumentation and explicit CRM attribution evidence.

    Creating a TrackingLink is instrumentation only. It is not click evidence. A CRM record
    becomes attributed only when the exact bm_tid/tracking_code is captured and bound through
    an AttributionClaim. The store never infers attribution from dates or provider metrics.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.links_root = self.root / "links"
        self.claims_root = self.root / "claims"
        self.links_root.mkdir(parents=True, exist_ok=True)
        self.claims_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _path(root: Path, row_id: str, pattern: re.Pattern[str]) -> Path:
        value = str(row_id or "").strip()
        if not pattern.fullmatch(value):
            raise ValueError("invalid attribution record id")
        return root / f"{value}.json"

    @staticmethod
    def _load(path: Path, cls):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid attribution payload")
        _assert_secret_free(payload)
        return cls(**payload)

    def create_link(self, company_id: str, payload: dict) -> TrackingLink:
        company = _company(company_id)
        if not isinstance(payload, dict):
            raise ValueError("tracking link payload must be an object")
        allowed = {
            "campaign_id", "creative_media_id", "destination_url", "utm_source", "utm_medium",
            "utm_campaign", "utm_id", "utm_content", "utm_term", "utm_source_platform",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported tracking link fields: {', '.join(sorted(unknown))}")
        campaign_id = _id(payload.get("campaign_id"), CAMPAIGN_ID_RE, field="campaign_id", required=True) or ""
        creative_media_id = _id(payload.get("creative_media_id"), MEDIA_ID_RE, field="creative_media_id")
        destination_url = _destination(payload.get("destination_url"))
        source = _utm(payload.get("utm_source"), field="utm_source", required=True) or ""
        medium = _utm(payload.get("utm_medium"), field="utm_medium", required=True) or ""
        campaign = _utm(payload.get("utm_campaign"), field="utm_campaign", required=True) or ""
        utm_id = _utm(payload.get("utm_id"), field="utm_id", required=True) or ""
        content = _utm(payload.get("utm_content"), field="utm_content")
        term = _utm(payload.get("utm_term"), field="utm_term")
        platform = _utm(payload.get("utm_source_platform"), field="utm_source_platform")
        row_id = f"tracking_{uuid.uuid4().hex[:24]}"
        code = f"bm_{uuid.uuid4().hex[:24]}"
        tracked = build_tracked_url(
            destination_url,
            tracking_code=code,
            utm_source=source,
            utm_medium=medium,
            utm_campaign=campaign,
            utm_id=utm_id,
            utm_content=content,
            utm_term=term,
            utm_source_platform=platform,
        )
        row = TrackingLink(
            schema=TRACKING_LINK_SCHEMA,
            id=row_id,
            company_id=company,
            campaign_id=campaign_id,
            creative_media_id=creative_media_id,
            destination_url=destination_url,
            tracked_url=tracked,
            tracking_code=code,
            utm_source=source,
            utm_medium=medium,
            utm_campaign=campaign,
            utm_id=utm_id,
            utm_content=content,
            utm_term=term,
            utm_source_platform=platform,
            created_at=_now(),
        )
        with self._lock:
            write_json_atomic(self._path(self.links_root, row.id, TRACKING_LINK_ID_RE), asdict(row))
        return row

    def get_link(self, company_id: str, link_id: str) -> TrackingLink:
        company = _company(company_id)
        with self._lock:
            path = self._path(self.links_root, link_id, TRACKING_LINK_ID_RE)
            if not path.is_file():
                raise KeyError(link_id)
            row = self._load(path, TrackingLink)
        if row.company_id != company:
            raise KeyError(link_id)
        return row

    def get_link_by_code(self, company_id: str, tracking_code: str) -> TrackingLink:
        company = _company(company_id)
        code = _id(tracking_code, TRACKING_CODE_RE, field="tracking_code", required=True) or ""
        for row in self.list_links(company):
            if row.tracking_code == code:
                return row
        raise KeyError(code)

    def list_links(self, company_id: str) -> list[TrackingLink]:
        company = _company(company_id)
        with self._lock:
            rows = [self._load(path, TrackingLink) for path in self.links_root.glob("tracking_*.json")]
        rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.created_at, row.id), reverse=True)

    def create_claim(self, company_id: str, payload: dict) -> AttributionClaim:
        company = _company(company_id)
        if not isinstance(payload, dict):
            raise ValueError("attribution claim payload must be an object")
        allowed = {"tracking_code", "contact_id", "opportunity_id", "evidence", "captured_at"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported attribution claim fields: {', '.join(sorted(unknown))}")
        code = _id(payload.get("tracking_code"), TRACKING_CODE_RE, field="tracking_code", required=True) or ""
        link = self.get_link_by_code(company, code)
        contact_id = _id(payload.get("contact_id"), CONTACT_ID_RE, field="contact_id")
        opportunity_id = _id(payload.get("opportunity_id"), OPPORTUNITY_ID_RE, field="opportunity_id")
        if not contact_id and not opportunity_id:
            raise ValueError("attribution claim requires a contact_id or opportunity_id")
        evidence = str(payload.get("evidence") or "CAPTURED_TRACKING_CODE").strip().upper()
        if evidence not in ATTRIBUTION_EVIDENCE:
            raise ValueError("unsupported attribution evidence")
        captured_at = _timestamp(payload.get("captured_at"), field="captured_at")
        with self._lock:
            for current in self.list_claims(company):
                if (
                    current.tracking_link_id == link.id
                    and current.contact_id == contact_id
                    and current.opportunity_id == opportunity_id
                ):
                    return current
            row = AttributionClaim(
                schema=ATTRIBUTION_CLAIM_SCHEMA,
                id=f"attribution_{uuid.uuid4().hex[:24]}",
                company_id=company,
                tracking_link_id=link.id,
                tracking_code=link.tracking_code,
                contact_id=contact_id,
                opportunity_id=opportunity_id,
                evidence=evidence,
                captured_at=captured_at,
                created_at=_now(),
            )
            write_json_atomic(self._path(self.claims_root, row.id, ATTRIBUTION_CLAIM_ID_RE), asdict(row))
            return row

    def list_claims(self, company_id: str) -> list[AttributionClaim]:
        company = _company(company_id)
        with self._lock:
            rows = [self._load(path, AttributionClaim) for path in self.claims_root.glob("attribution_*.json")]
        rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.captured_at, row.created_at, row.id), reverse=True)


__all__ = [
    "ATTRIBUTION_CLAIM_SCHEMA",
    "ATTRIBUTION_EVIDENCE",
    "AttributionClaim",
    "AttributionStore",
    "TRACKING_LINK_SCHEMA",
    "TrackingLink",
    "build_tracked_url",
]
