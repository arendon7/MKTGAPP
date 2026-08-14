from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .crm_store import CONTACT_ID_RE
from .social_store import _now


AUDIENCE_ID_RE = re.compile(r"^audience_[0-9a-f]{24}$")


def _text(value: object, limit: int, *, required: bool = False, field: str = "value") -> str | None:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > limit:
        raise ValueError(f"{field} is too long")
    return result or None


def _contact_ids(value: object) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, (list, tuple)):
        raise ValueError("contact_ids must be an array")
    result: list[str] = []
    for raw in value:
        contact_id = str(raw or "").strip()
        if not CONTACT_ID_RE.fullmatch(contact_id):
            raise ValueError("invalid contact id in audience")
        if contact_id not in result:
            result.append(contact_id)
    if len(result) > 10000:
        raise ValueError("audience exceeds 10000 contacts")
    return tuple(result)


@dataclass(frozen=True)
class Audience:
    id: str
    company_id: str
    name: str
    description: str | None
    contact_ids: tuple[str, ...]
    created_at: str
    updated_at: str


class AudienceStore:
    """Durable static CRM audiences. No audience operation sends messages."""

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
    def _audience_id(value: str) -> str:
        audience_id = str(value or "").strip()
        if not AUDIENCE_ID_RE.fullmatch(audience_id):
            raise ValueError("invalid audience id")
        return audience_id

    def _path(self, audience_id: str) -> Path:
        return self.root / f"{self._audience_id(audience_id)}.json"

    @staticmethod
    def _load(path: Path) -> Audience:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid audience payload")
        payload["contact_ids"] = tuple(payload.get("contact_ids") or ())
        return Audience(**payload)

    def create(self, company_id: str, payload: dict) -> Audience:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("audience payload must be an object")
        allowed = {"name", "description", "contact_ids"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported audience fields: {', '.join(sorted(unknown))}")
        now = _now()
        row = Audience(
            id=f"audience_{uuid.uuid4().hex[:24]}",
            company_id=company,
            name=_text(payload.get("name"), 180, required=True, field="audience name") or "",
            description=_text(payload.get("description"), 2000),
            contact_ids=_contact_ids(payload.get("contact_ids")),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._path(row.id), asdict(row))
        return row

    def get(self, audience_id: str) -> Audience:
        with self._lock:
            path = self._path(audience_id)
            if not path.is_file():
                raise KeyError(audience_id)
            return self._load(path)

    def get_for_company(self, company_id: str, audience_id: str) -> Audience:
        company = self._company_id(company_id)
        row = self.get(audience_id)
        if row.company_id != company:
            raise KeyError(audience_id)
        return row

    def list(self, company_id: str | None = None) -> list[Audience]:
        company = self._company_id(company_id) if company_id else None
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("audience_*.json")]
        if company:
            rows = [row for row in rows if row.company_id == company]
        return sorted(rows, key=lambda row: (row.name.casefold(), row.id))

    def update(self, company_id: str, audience_id: str, payload: dict) -> Audience:
        company = self._company_id(company_id)
        if not isinstance(payload, dict):
            raise ValueError("audience payload must be an object")
        allowed = {"name", "description", "contact_ids"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported audience fields: {', '.join(sorted(unknown))}")
        with self._lock:
            current = self.get_for_company(company, audience_id)
            row = Audience(
                id=current.id,
                company_id=current.company_id,
                name=(
                    _text(payload.get("name"), 180, required=True, field="audience name") or ""
                    if "name" in payload else current.name
                ),
                description=(
                    _text(payload.get("description"), 2000)
                    if "description" in payload else current.description
                ),
                contact_ids=(
                    _contact_ids(payload.get("contact_ids"))
                    if "contact_ids" in payload else current.contact_ids
                ),
                created_at=current.created_at,
                updated_at=_now(),
            )
            write_json_atomic(self._path(row.id), asdict(row))
            return row

    def delete(self, company_id: str, audience_id: str) -> Audience:
        company = self._company_id(company_id)
        with self._lock:
            row = self.get_for_company(company, audience_id)
            self._path(row.id).unlink(missing_ok=True)
            return row

    def summary(self, company_id: str | None = None) -> dict:
        rows = self.list(company_id)
        members = {contact_id for row in rows for contact_id in row.contact_ids}
        return {
            "total": len(rows),
            "unique_contacts": len(members),
            "memberships": sum(len(row.contact_ids) for row in rows),
        }


__all__ = ["AUDIENCE_ID_RE", "Audience", "AudienceStore"]
