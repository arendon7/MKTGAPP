from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic


STORE_SCHEMA = "binario.marketing.pilot-incidents.v1"
EVENT_SCHEMA = "binario.marketing.pilot-incident-event.v1"
MODULES = (
    "STARTUP",
    "TODAY",
    "COMPANIES",
    "CONTENT",
    "CALENDAR",
    "CRM",
    "INBOX",
    "CAMPAIGNS",
    "PAID_MEDIA",
    "RESULTS",
    "VIDEO",
    "AI",
    "BACKUP",
)
CATEGORIES = ("UI", "DATA", "WORKFLOW", "PERFORMANCE", "INTEGRATION", "STARTUP", "RECOVERY")
SEVERITIES = ("LOW", "MEDIUM", "HIGH", "BLOCKING")
EVENT_TYPES = ("OPENED", "RESOLVED")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INCIDENT_RE = re.compile(r"^incident_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")
_EVENT_RE = re.compile(r"^event_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")


class PilotIncidentLogCorrupt(RuntimeError):
    """Raised when persisted pilot incident events cannot be trusted."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str, now: datetime) -> str:
    return f"{prefix}_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def _validate_date(value: object) -> str:
    local_date = str(value or "")
    if not _DATE_RE.fullmatch(local_date):
        raise ValueError("pilot incident date must be YYYY-MM-DD")
    try:
        datetime.strptime(local_date, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("pilot incident date is invalid") from exc
    return local_date


def _enum(value: object, allowed: tuple[str, ...], label: str) -> str:
    normalized = str(value or "").upper()
    if normalized not in allowed:
        raise ValueError(f"pilot incident {label} is invalid")
    return normalized


class PilotIncidentLog:
    """Append-only structured incident evidence for the local pilot.

    No event accepts free-form text, company/contact identifiers, provider metadata,
    filesystem metadata, content payloads, credentials, or execution instructions.
    Resolution appends a second event; historical events are never edited or deleted.
    """

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().absolute()
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict:
        return {"schema": STORE_SCHEMA, "events": []}

    def _read(self) -> dict:
        if not self.path.exists():
            return self._empty()
        try:
            if self.path.is_symlink() or not self.path.is_file():
                raise ValueError("unsafe pilot incident store")
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or set(payload) != {"schema", "events"}:
                raise ValueError("invalid pilot incident store")
            if payload.get("schema") != STORE_SCHEMA or not isinstance(payload.get("events"), list):
                raise ValueError("invalid pilot incident store")
            for event in payload["events"]:
                self._validate_stored_event(event)
            self._derive(payload["events"])
            return payload
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
            raise PilotIncidentLogCorrupt("pilot incident store failed integrity validation") from exc

    @staticmethod
    def _validate_stored_event(event: object) -> None:
        if not isinstance(event, dict):
            raise ValueError("invalid pilot incident event")
        event_type = str(event.get("type") or "")
        if event_type == "OPENED":
            expected = {
                "schema", "event_id", "incident_id", "type", "recorded_at", "local_date",
                "module", "category", "severity",
            }
        elif event_type == "RESOLVED":
            expected = {"schema", "event_id", "incident_id", "type", "recorded_at", "local_date"}
        else:
            raise ValueError("invalid pilot incident event type")
        if set(event) != expected or event.get("schema") != EVENT_SCHEMA:
            raise ValueError("invalid pilot incident event")
        if not _EVENT_RE.fullmatch(str(event.get("event_id") or "")):
            raise ValueError("invalid pilot incident event id")
        if not _INCIDENT_RE.fullmatch(str(event.get("incident_id") or "")):
            raise ValueError("invalid pilot incident id")
        _validate_date(event.get("local_date"))
        timestamp = datetime.fromisoformat(str(event.get("recorded_at") or "").replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError("invalid pilot incident timestamp")
        if event_type == "OPENED":
            _enum(event.get("module"), MODULES, "module")
            _enum(event.get("category"), CATEGORIES, "category")
            _enum(event.get("severity"), SEVERITIES, "severity")

    @staticmethod
    def _derive(events: list[dict]) -> list[dict]:
        incidents: dict[str, dict] = {}
        order: list[str] = []
        for event in events:
            incident_id = event["incident_id"]
            if event["type"] == "OPENED":
                if incident_id in incidents:
                    raise ValueError("duplicate pilot incident opening")
                incidents[incident_id] = {
                    "schema": "binario.marketing.pilot-incident.v1",
                    "id": incident_id,
                    "opened_at": event["recorded_at"],
                    "opened_date": event["local_date"],
                    "module": event["module"],
                    "category": event["category"],
                    "severity": event["severity"],
                    "status": "OPEN",
                    "resolved_at": None,
                    "resolved_date": None,
                }
                order.append(incident_id)
                continue
            incident = incidents.get(incident_id)
            if incident is None or incident["status"] != "OPEN":
                raise ValueError("invalid pilot incident resolution sequence")
            incident["status"] = "RESOLVED"
            incident["resolved_at"] = event["recorded_at"]
            incident["resolved_date"] = event["local_date"]
        return [incidents[incident_id] for incident_id in order]

    def open(self, payload: object) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"local_date", "module", "category", "severity"}:
            raise ValueError("pilot incident payload has unsupported fields")
        local_date = _validate_date(payload.get("local_date"))
        module = _enum(payload.get("module"), MODULES, "module")
        category = _enum(payload.get("category"), CATEGORIES, "category")
        severity = _enum(payload.get("severity"), SEVERITIES, "severity")
        now = _now()
        incident_id = _id("incident", now)
        event = {
            "schema": EVENT_SCHEMA,
            "event_id": _id("event", now),
            "incident_id": incident_id,
            "type": "OPENED",
            "recorded_at": now.isoformat(),
            "local_date": local_date,
            "module": module,
            "category": category,
            "severity": severity,
        }
        with self._lock:
            store = self._read()
            store["events"].append(event)
            write_json_atomic(self.path, store)
        return self.get(incident_id)

    def resolve(self, incident_id: str, payload: object) -> dict:
        target = str(incident_id or "")
        if not _INCIDENT_RE.fullmatch(target):
            raise ValueError("pilot incident id is invalid")
        if not isinstance(payload, dict) or set(payload) != {"local_date"}:
            raise ValueError("pilot incident resolution payload has unsupported fields")
        local_date = _validate_date(payload.get("local_date"))
        with self._lock:
            store = self._read()
            current = next((row for row in self._derive(store["events"]) if row["id"] == target), None)
            if current is None:
                raise KeyError("pilot incident not found")
            if current["status"] != "OPEN":
                raise ValueError("pilot incident is already resolved")
            now = _now()
            store["events"].append({
                "schema": EVENT_SCHEMA,
                "event_id": _id("event", now),
                "incident_id": target,
                "type": "RESOLVED",
                "recorded_at": now.isoformat(),
                "local_date": local_date,
            })
            write_json_atomic(self.path, store)
        return self.get(target)

    def get(self, incident_id: str) -> dict:
        target = str(incident_id or "")
        if not _INCIDENT_RE.fullmatch(target):
            raise ValueError("pilot incident id is invalid")
        with self._lock:
            incident = next((row for row in self._derive(self._read()["events"]) if row["id"] == target), None)
        if incident is None:
            raise KeyError("pilot incident not found")
        return dict(incident)

    def list(self, *, status: str = "ALL", limit: int = 100) -> dict:
        normalized_status = str(status or "ALL").upper()
        if normalized_status not in {"ALL", "OPEN", "RESOLVED"}:
            raise ValueError("pilot incident status filter is invalid")
        if isinstance(limit, bool):
            raise ValueError("pilot incident limit is invalid")
        requested = int(limit)
        if requested < 1 or requested > 365:
            raise ValueError("pilot incident limit is out of range")
        with self._lock:
            rows = self._derive(self._read()["events"])
        rows.sort(key=lambda row: (row["opened_at"], row["id"]), reverse=True)
        open_count = sum(1 for row in rows if row["status"] == "OPEN")
        blocking_open = sum(1 for row in rows if row["status"] == "OPEN" and row["severity"] == "BLOCKING")
        high_open = sum(1 for row in rows if row["status"] == "OPEN" and row["severity"] == "HIGH")
        filtered = rows if normalized_status == "ALL" else [row for row in rows if row["status"] == normalized_status]
        return {
            "schema": STORE_SCHEMA,
            "incidents": [dict(row) for row in filtered[:requested]],
            "summary": {
                "incident_count": len(rows),
                "open_count": open_count,
                "resolved_count": len(rows) - open_count,
                "blocking_open": blocking_open,
                "high_open": high_open,
            },
            "safety": {
                "local_only": True,
                "free_text_stored": False,
                "identity_fields_stored": False,
                "provider_metadata_stored": False,
                "content_payloads_stored": False,
                "delete_authority": False,
                "execution_authority": False,
            },
        }


__all__ = [
    "CATEGORIES",
    "EVENT_SCHEMA",
    "EVENT_TYPES",
    "MODULES",
    "PilotIncidentLog",
    "PilotIncidentLogCorrupt",
    "SEVERITIES",
    "STORE_SCHEMA",
]
