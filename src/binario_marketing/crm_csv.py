from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict

from .crm_store import CRMStore, Contact


MAX_CSV_BYTES = 2_000_000
MAX_CSV_ROWS = 5_000
EXPORT_HEADERS = (
    "nombre",
    "empresa",
    "cargo",
    "email",
    "telefono",
    "whatsapp",
    "instagram",
    "origen",
    "etiquetas",
    "notas",
)
ALIASES = {
    "nombre": "name", "name": "name", "contacto": "name",
    "empresa": "organization", "organizacion": "organization", "organización": "organization", "organization": "organization", "company": "organization",
    "cargo": "role", "rol": "role", "role": "role", "position": "role",
    "email": "email", "correo": "email", "correo electronico": "email", "correo electrónico": "email",
    "telefono": "phone", "teléfono": "phone", "phone": "phone", "celular": "phone", "movil": "phone", "móvil": "phone",
    "whatsapp": "whatsapp", "wa": "whatsapp",
    "instagram": "instagram", "ig": "instagram",
    "origen": "source", "source": "source", "fuente": "source",
    "etiquetas": "tags", "tags": "tags", "tag": "tags",
    "notas": "notes", "notes": "notes", "observaciones": "notes",
}
EXPORT_FIELDS = {
    "nombre": "name",
    "empresa": "organization",
    "cargo": "role",
    "email": "email",
    "telefono": "phone",
    "whatsapp": "whatsapp",
    "instagram": "instagram",
    "origen": "source",
    "etiquetas": "tags",
    "notas": "notes",
}


def _header(value: object) -> str:
    return " ".join(str(value or "").strip().casefold().replace("_", " ").replace("-", " ").split())


def _cell(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    # Undo only the spreadsheet-injection guard produced by export_contacts_csv.
    if text.startswith("\u200b") and len(text) > 1 and text[1] in "=+-@":
        text = text[1:]
    return text


def _tags(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[|,;]", value)
    result: list[str] = []
    seen: set[str] = set()
    for raw in parts:
        tag = raw.strip()
        if tag and tag.casefold() not in seen:
            result.append(tag)
            seen.add(tag.casefold())
    return result


def _identity_tokens(payload: dict) -> set[str]:
    result: set[str] = set()
    email = str(payload.get("email") or "").strip().casefold()
    if email:
        result.add(f"email:{email}")
    for field in ("phone", "whatsapp"):
        raw = str(payload.get(field) or "").strip()
        digits = "".join(ch for ch in raw if ch.isdigit())
        if len(digits) >= 7:
            result.add(f"phone:{digits}")
    instagram = str(payload.get("instagram") or "").strip().lstrip("@").casefold()
    if instagram:
        result.add(f"instagram:{instagram}")
    if not result:
        name = str(payload.get("name") or "").strip().casefold()
        organization = str(payload.get("organization") or "").strip().casefold()
        if name:
            result.add(f"fallback:{name}|{organization}")
    return result


def _existing_tokens(rows: list[Contact]) -> set[str]:
    result: set[str] = set()
    for row in rows:
        result.update(_identity_tokens(asdict(row)))
    return result


def _decode_csv(value: object) -> str:
    text = str(value or "")
    if not text.strip():
        raise ValueError("CSV content is required")
    raw = text.encode("utf-8")
    if len(raw) > MAX_CSV_BYTES:
        raise ValueError("CSV is larger than 2 MB")
    return text.lstrip("\ufeff")


def _reader(text: str) -> tuple[csv.DictReader, dict[str, str]]:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV header row is required")
    mapping: dict[str, str] = {}
    for original in reader.fieldnames:
        canonical = ALIASES.get(_header(original))
        if canonical and canonical not in mapping.values():
            mapping[str(original)] = canonical
    if "name" not in mapping.values():
        raise ValueError("CSV must include a nombre/name column")
    return reader, mapping


def parse_contacts_csv(text: object) -> list[dict]:
    decoded = _decode_csv(text)
    reader, mapping = _reader(decoded)
    rows: list[dict] = []
    for line_number, raw in enumerate(reader, start=2):
        if line_number > MAX_CSV_ROWS + 1:
            raise ValueError(f"CSV exceeds {MAX_CSV_ROWS} contact rows")
        payload = {field: _cell(raw.get(source)) for source, field in mapping.items()}
        if not any(payload.values()):
            continue
        payload["tags"] = _tags(str(payload.get("tags") or ""))
        rows.append({"line": line_number, "payload": payload})
    return rows


def preview_contacts_csv(store: CRMStore, company_id: str, text: object) -> dict:
    rows = parse_contacts_csv(text)
    existing = _existing_tokens(store.list_contacts(company_id))
    seen: set[str] = set()
    valid = duplicates = invalid = 0
    errors: list[dict] = []
    for item in rows:
        payload = item["payload"]
        try:
            # Reuse CRMStore validation without persisting by validating through its field rules indirectly.
            if not str(payload.get("name") or "").strip():
                raise ValueError("contact name is required")
            if len(str(payload.get("name") or "")) > 160:
                raise ValueError("contact name is too long")
            if len(payload.get("tags") or []) > 30 or any(len(tag) > 40 for tag in payload.get("tags") or []):
                raise ValueError("invalid tags")
            for field, limit in (("organization",160),("role",120),("email",254),("phone",80),("whatsapp",80),("instagram",120),("source",120),("notes",5000)):
                if len(str(payload.get(field) or "")) > limit:
                    raise ValueError(f"{field} is too long")
            tokens = _identity_tokens(payload)
            if tokens & existing or tokens & seen:
                duplicates += 1
                continue
            seen.update(tokens)
            valid += 1
        except ValueError as exc:
            invalid += 1
            if len(errors) < 25:
                errors.append({"line": item["line"], "error": str(exc)})
    return {
        "schema": "binario.marketing.crm-csv-preview.v1",
        "rows": len(rows),
        "valid": valid,
        "duplicates": duplicates,
        "invalid": invalid,
        "errors": errors,
    }


def import_contacts_csv(store: CRMStore, company_id: str, text: object) -> dict:
    rows = parse_contacts_csv(text)
    existing = _existing_tokens(store.list_contacts(company_id))
    seen: set[str] = set()
    created: list[Contact] = []
    duplicates = invalid = 0
    errors: list[dict] = []
    for item in rows:
        payload = item["payload"]
        tokens = _identity_tokens(payload)
        if tokens & existing or tokens & seen:
            duplicates += 1
            continue
        try:
            row = store.create_contact(company_id, payload)
        except ValueError as exc:
            invalid += 1
            if len(errors) < 25:
                errors.append({"line": item["line"], "error": str(exc)})
            continue
        created.append(row)
        seen.update(tokens)
        existing.update(tokens)
    return {
        "schema": "binario.marketing.crm-csv-import.v1",
        "rows": len(rows),
        "created": len(created),
        "duplicates": duplicates,
        "invalid": invalid,
        "errors": errors,
        "contact_ids": [row.id for row in created],
    }


def _safe_export_cell(value: object) -> str:
    if isinstance(value, (list, tuple)):
        text = " | ".join(str(item) for item in value)
    else:
        text = str(value or "")
    if text.startswith(("=", "+", "-", "@")):
        return "\u200b" + text
    return text


def export_contacts_csv(store: CRMStore, company_id: str) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=EXPORT_HEADERS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    for row in store.list_contacts(company_id):
        data = asdict(row)
        writer.writerow({header: _safe_export_cell(data.get(field)) for header, field in EXPORT_FIELDS.items()})
    return "\ufeff" + output.getvalue()
