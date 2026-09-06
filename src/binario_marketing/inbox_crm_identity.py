from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .crm_store import CONTACT_ID_RE
from .social_store import _now


_SCHEMA = "binario.marketing.inbox-crm-identity-link.v1"
_PROVIDERS = {"facebook", "instagram"}


class InboxCRMIdentityConflict(RuntimeError):
    """Raised when an explicit identity link would overwrite newer local evidence."""


@dataclass(frozen=True)
class InboxCRMIdentityLink:
    schema: str
    company_id: str
    provider: str
    fingerprint: str
    contact_id: str
    created_at: str
    updated_at: str


class InboxCRMIdentityStore:
    """Company-scoped social identity links without persisting provider person ids.

    Provider ids are used transiently to derive a keyed HMAC fingerprint. The raw id
    is never written to disk, returned by this store, or required by CRM records.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.links_root = self.root / "links"
        self.links_root.mkdir(parents=True, exist_ok=True)
        self.key_path = self.root / ".identity-key"
        self._lock = threading.RLock()

    @staticmethod
    def _company(value: object) -> str:
        company = str(value or "").strip()
        if not COMPANY_ID_RE.fullmatch(company):
            raise ValueError("invalid company id")
        return company

    @staticmethod
    def _provider(value: object) -> str:
        provider = str(value or "").strip().lower()
        if provider not in _PROVIDERS:
            raise ValueError("provider must be facebook or instagram")
        return provider

    @staticmethod
    def _person_id(value: object) -> str:
        person = str(value or "").strip()
        if not person:
            raise ValueError("provider person id is required")
        if len(person) > 300 or any(ord(ch) < 33 or ord(ch) == 127 for ch in person):
            raise ValueError("invalid provider person id")
        return person

    @staticmethod
    def _contact(value: object) -> str:
        contact = str(value or "").strip()
        if not CONTACT_ID_RE.fullmatch(contact):
            raise ValueError("invalid CRM contact id")
        return contact

    def _read_key(self) -> bytes:
        try:
            key = self.key_path.read_bytes()
        except FileNotFoundError:
            raise
        if len(key) != 32:
            raise ValueError("invalid Inbox CRM identity key")
        if os.name == "posix":
            os.chmod(self.key_path, 0o600)
            if self.key_path.stat().st_mode & 0o077:
                raise ValueError("Inbox CRM identity key permissions are unsafe")
        return key

    def _key(self) -> bytes:
        with self._lock:
            try:
                return self._read_key()
            except FileNotFoundError:
                key = secrets.token_bytes(32)
                self.root.mkdir(parents=True, exist_ok=True)
                flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
                try:
                    fd = os.open(self.key_path, flags, 0o600)
                except FileExistsError:
                    return self._read_key()
                try:
                    with os.fdopen(fd, "wb") as handle:
                        handle.write(key)
                        handle.flush()
                        os.fsync(handle.fileno())
                except Exception:
                    try:
                        self.key_path.unlink()
                    except OSError:
                        pass
                    raise
                if os.name == "posix":
                    os.chmod(self.key_path, 0o600)
                return key

    def fingerprint(self, company_id: object, provider: object, provider_person_id: object) -> str:
        company = self._company(company_id)
        channel = self._provider(provider)
        person = self._person_id(provider_person_id)
        message = f"binario-inbox-crm-v1\0{company}\0{channel}\0{person}".encode("utf-8")
        return hmac.new(self._key(), message, hashlib.sha256).hexdigest()

    def _path(self, fingerprint: str) -> Path:
        value = str(fingerprint or "").strip().lower()
        if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
            raise ValueError("invalid identity fingerprint")
        return self.links_root / f"{value}.json"

    def _load(self, path: Path) -> InboxCRMIdentityLink:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid Inbox CRM identity link")
        row = InboxCRMIdentityLink(**payload)
        if (
            row.schema != _SCHEMA
            or not COMPANY_ID_RE.fullmatch(row.company_id)
            or row.provider not in _PROVIDERS
            or not CONTACT_ID_RE.fullmatch(row.contact_id)
            or row.fingerprint != path.stem
        ):
            raise ValueError("invalid Inbox CRM identity link")
        return row

    def get(self, company_id: object, provider: object, provider_person_id: object) -> InboxCRMIdentityLink | None:
        company = self._company(company_id)
        channel = self._provider(provider)
        fingerprint = self.fingerprint(company, channel, provider_person_id)
        with self._lock:
            path = self._path(fingerprint)
            if not path.is_file():
                return None
            row = self._load(path)
            if row.company_id != company or row.provider != channel:
                raise ValueError("identity link scope mismatch")
            return row

    def link(
        self,
        company_id: object,
        provider: object,
        provider_person_id: object,
        contact_id: object,
        *,
        expected_contact_id: object | None = None,
        replace_confirmed: bool = False,
    ) -> tuple[InboxCRMIdentityLink, bool]:
        company = self._company(company_id)
        channel = self._provider(provider)
        contact = self._contact(contact_id)
        expected = None if expected_contact_id in (None, "") else self._contact(expected_contact_id)
        if not isinstance(replace_confirmed, bool):
            raise ValueError("replace_confirmed must be boolean")
        fingerprint = self.fingerprint(company, channel, provider_person_id)
        with self._lock:
            path = self._path(fingerprint)
            current = self._load(path) if path.is_file() else None
            if current is not None:
                if current.company_id != company or current.provider != channel:
                    raise ValueError("identity link scope mismatch")
                if current.contact_id == contact:
                    return current, True
                if not replace_confirmed or expected != current.contact_id:
                    raise InboxCRMIdentityConflict(
                        "This social identity is already linked to another CRM contact. Refresh Inbox and explicitly confirm the replacement."
                    )
                row = replace(current, contact_id=contact, updated_at=_now())
                write_json_atomic(path, asdict(row))
                return row, False
            if expected is not None or replace_confirmed:
                raise InboxCRMIdentityConflict("identity link changed before confirmation; refresh Inbox before linking")
            now = _now()
            row = InboxCRMIdentityLink(
                schema=_SCHEMA,
                company_id=company,
                provider=channel,
                fingerprint=fingerprint,
                contact_id=contact,
                created_at=now,
                updated_at=now,
            )
            write_json_atomic(path, asdict(row))
            return row, False


__all__ = ["InboxCRMIdentityConflict", "InboxCRMIdentityLink", "InboxCRMIdentityStore"]
