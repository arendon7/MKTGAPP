from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict

from .crm_store import CRMStore, Contact


MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_CSV_ROWS = 10000
CSV_FIELDS = ("name", "organization", "role", "email", "phone", "whatsapp", "instagram", "source", "tags", "notes")
CSV_ALIASES = {
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
}


def _header(value: str) -> str:
    return str(value or "").strip().casefold().replace(" ", "_")


def _clean(value: object) -> str | None:
    result = str(value or "").strip()
    return result or None


def _email(value: object) -> str | None:
    result = _clean(value)
    return result.casefold() if result else None


def _phone(value: object) -> str | None:
    result = _clean(value)
    if not result:
        return None
    plus = result.startswith("+")
    digits = re.sub(r"\D", "", result)
    if not digits:
        return None
    return f"+{digits}" if plus else digits


def _tags(value: object) -> list[str]:
    result = _clean(value)
    if not result:
        return []
    parts = re.split(r"[,;|]", result)
    tags: list[str] = []
    for raw in parts:
        tag = raw.strip()
        if tag and tag.casefold() not in {item.casefold() for item in tags}:
            tags.append(tag)
    return tags[:30]


def _identity_keys(payload: dict) -> list[tuple[str, str]]:
    keys: list[tuple[str, str]] = []
    email = _email(payload.get("email"))
    whatsapp = _phone(payload.get("whatsapp"))
    phone = _phone(payload.get("phone"))
    if email:
        keys.append(("email", email))
    if whatsapp:
        keys.append(("whatsapp", whatsapp))
    if phone:
        keys.append(("phone", phone))
    return keys


def _contact_keys(row: Contact) -> list[tuple[str, str]]:
    return _identity_keys(asdict(row))


def parse_contact_csv(content: bytes) -> tuple[list[tuple[int, dict]], list[dict]]:
    if not isinstance(content, (bytes, bytearray)):
        raise ValueError("CSV content must be bytes")
    if not content:
        raise ValueError("CSV file is empty")
    if len(content) > MAX_CSV_BYTES:
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
        normalized = _header(raw)
        field = CSV_ALIASES.get(normalized)
        if not field:
            raise ValueError(f"unsupported CSV column: {raw}")
        if field in mapped:
            raise ValueError(f"duplicate CSV column for {field}")
        mapped.append(field)
    if "name" not in mapped:
        raise ValueError("CSV requires a name/nombre column")

    rows: list[tuple[int, dict]] = []
    errors: list[dict] = []
    for index, raw_row in enumerate(reader, start=2):
        if index - 1 > MAX_CSV_ROWS:
            raise ValueError("CSV exceeds 10000 data rows")
        payload: dict = {}
        for source_name, field in zip(reader.fieldnames, mapped):
            value = _clean(raw_row.get(source_name))
            if field == "tags":
                payload[field] = _tags(value)
            elif value is not None:
                payload[field] = value
        if not payload.get("name"):
            errors.append({"row": index, "error": "name is required"})
            continue
        rows.append((index, payload))
    return rows, errors


class ContactCSVImporter:
    """Company-local CSV importer with deterministic duplicate handling."""

    def __init__(self, crm: CRMStore):
        self.crm = crm

    def import_bytes(self, company_id: str, content: bytes, *, strategy: str = "skip") -> dict:
        mode = str(strategy or "skip").strip().lower()
        if mode not in {"skip", "update"}:
            raise ValueError("CSV duplicate strategy must be skip or update")
        rows, parse_errors = parse_contact_csv(content)
        existing = self.crm.list_contacts(company_id)
        index: dict[tuple[str, str], str] = {}
        for contact in existing:
            for key in _contact_keys(contact):
                index[key] = contact.id

        created = 0
        updated = 0
        skipped = 0
        errors = list(parse_errors)
        imported_ids: list[str] = []
        for row_number, payload in rows:
            keys = _identity_keys(payload)
            matches = {index[key] for key in keys if key in index}
            if len(matches) > 1:
                errors.append({"row": row_number, "error": "identity fields match multiple existing contacts"})
                continue
            existing_id = next(iter(matches), None)
            try:
                if existing_id and mode == "skip":
                    skipped += 1
                    imported_ids.append(existing_id)
                    continue
                if existing_id:
                    current = self.crm.get_contact(existing_id)
                    patch = {key: value for key, value in payload.items() if key != "name" and value not in (None, "", [])}
                    if payload.get("name"):
                        patch["name"] = payload["name"]
                    if payload.get("tags"):
                        combined = list(current.tags)
                        for tag in payload["tags"]:
                            if tag.casefold() not in {item.casefold() for item in combined}:
                                combined.append(tag)
                        patch["tags"] = combined[:30]
                    contact = self.crm.update_contact(company_id, existing_id, patch)
                    updated += 1
                else:
                    contact = self.crm.create_contact(company_id, payload)
                    created += 1
                imported_ids.append(contact.id)
                for key in _contact_keys(contact):
                    index[key] = contact.id
            except (ValueError, TypeError) as exc:
                errors.append({"row": row_number, "error": str(exc)})
            if len(errors) >= 100:
                errors = errors[:100]
                break
        return {
            "strategy": mode,
            "rows": len(rows) + len(parse_errors),
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "errors": errors,
            "error_count": len(errors),
            "contact_ids": list(dict.fromkeys(imported_ids)),
        }


__all__ = [
    "CSV_FIELDS",
    "ContactCSVImporter",
    "MAX_CSV_BYTES",
    "MAX_CSV_ROWS",
    "parse_contact_csv",
]
