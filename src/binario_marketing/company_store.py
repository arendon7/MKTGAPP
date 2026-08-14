from __future__ import annotations

import re
import threading
import unicodedata
import uuid
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .atomic import write_json_atomic
from .social_store import _now


COMPANY_ID_RE = re.compile(r"^company_[0-9a-f]{24}$")
_ALLOWED_FIELDS = {
    "name",
    "facebook_page_id",
    "facebook_page_name",
    "instagram_id",
    "instagram_username",
    "ad_account_id",
    "ad_account_name",
    "active",
}


def _clean_optional(value: object, limit: int = 180) -> str | None:
    text = str(value or "").strip()
    return text[:limit] or None


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")
    return normalized[:64] or "empresa"


@dataclass(frozen=True)
class Company:
    id: str
    name: str
    slug: str
    active: bool
    facebook_page_id: str | None
    facebook_page_name: str | None
    instagram_id: str | None
    instagram_username: str | None
    ad_account_id: str | None
    ad_account_name: str | None
    created_at: str
    updated_at: str


class CompanyStore:
    """Durable non-secret company/brand registry for the marketing operations layer."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, company_id: str) -> Path:
        value = str(company_id or "").strip()
        if not COMPANY_ID_RE.fullmatch(value):
            raise ValueError("invalid company id")
        return self.root / f"{value}.json"

    def _load(self, path: Path) -> Company:
        import json

        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid company payload")
        row = Company(**payload)
        if not COMPANY_ID_RE.fullmatch(row.id):
            raise ValueError("invalid company record")
        return row

    def create(self, name: str) -> Company:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("company name is required")
        if len(clean_name) > 160:
            raise ValueError("company name is too long")
        now = _now()
        row = Company(
            id=f"company_{uuid.uuid4().hex[:24]}",
            name=clean_name,
            slug=_slug(clean_name),
            active=True,
            facebook_page_id=None,
            facebook_page_name=None,
            instagram_id=None,
            instagram_username=None,
            ad_account_id=None,
            ad_account_name=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._path(row.id), asdict(row))
        return row

    def get(self, company_id: str) -> Company:
        with self._lock:
            path = self._path(company_id)
            if not path.is_file():
                raise KeyError(company_id)
            return self._load(path)

    def list(self, *, include_inactive: bool = False) -> list[Company]:
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("company_*.json")]
        if not include_inactive:
            rows = [row for row in rows if row.active]
        return sorted(rows, key=lambda row: (row.name.casefold(), row.id))

    def update(self, company_id: str, payload: dict) -> Company:
        if not isinstance(payload, dict):
            raise ValueError("company payload must be an object")
        unknown = set(payload) - _ALLOWED_FIELDS
        if unknown:
            raise ValueError(f"unsupported company fields: {', '.join(sorted(unknown))}")
        with self._lock:
            current = self.get(company_id)
            values = asdict(current)
            if "name" in payload:
                name = str(payload.get("name") or "").strip()
                if not name:
                    raise ValueError("company name is required")
                if len(name) > 160:
                    raise ValueError("company name is too long")
                values["name"] = name
                values["slug"] = _slug(name)
            for field in (
                "facebook_page_id",
                "facebook_page_name",
                "instagram_id",
                "instagram_username",
                "ad_account_id",
                "ad_account_name",
            ):
                if field in payload:
                    values[field] = _clean_optional(payload[field])
            if "active" in payload:
                if not isinstance(payload["active"], bool):
                    raise ValueError("active must be boolean")
                values["active"] = payload["active"]
            values["updated_at"] = _now()
            row = Company(**values)
            write_json_atomic(self._path(row.id), asdict(row))
            return row


__all__ = ["COMPANY_ID_RE", "Company", "CompanyStore"]
