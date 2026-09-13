from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic


STORE_SCHEMA = "binario.marketing.pilot-daily-receipts.v1"
RECEIPT_SCHEMA = "binario.marketing.pilot-daily-receipt.v1"
GATE_SCHEMA = "binario.marketing.pilot-launch-gate.v1"
CHECK_IDS = ("runtime", "companies", "journey", "snapshot", "recovery")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_RECEIPT_RE = re.compile(r"^receipt_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _receipt_id(now: datetime) -> str:
    return f"receipt_{now.strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}"


def _bounded_int(value: object, *, minimum: int = 0, maximum: int = 10000) -> int:
    if isinstance(value, bool):
        raise ValueError("pilot receipt numeric field is invalid")
    number = int(value)
    if number < minimum or number > maximum:
        raise ValueError("pilot receipt numeric field is out of range")
    return number


class PilotDailyReceiptStore:
    """Append-only, local-only minimized evidence for a multi-day pilot.

    The store intentionally accepts no free-form notes, company/contact identifiers,
    provider metadata, filesystem paths, hashes, credentials, or content payloads.
    Receipts are operational observations only and never grant execution authority.
    """

    def __init__(self, path: Path):
        self.path = Path(path).expanduser().resolve()
        self._lock = threading.RLock()

    @staticmethod
    def _empty() -> dict:
        return {"schema": STORE_SCHEMA, "receipts": []}

    def _read(self) -> dict:
        if self.path.is_symlink():
            raise ValueError("pilot receipt store must not be a symbolic link")
        if not self.path.exists():
            return self._empty()
        if not self.path.is_file():
            raise ValueError("pilot receipt store must be a regular file")
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or set(payload) != {"schema", "receipts"}:
            raise ValueError("invalid pilot receipt store")
        if payload.get("schema") != STORE_SCHEMA or not isinstance(payload.get("receipts"), list):
            raise ValueError("invalid pilot receipt store")
        for row in payload["receipts"]:
            self._validate_stored(row)
        return payload

    @staticmethod
    def _sanitize_gate(payload: object) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("pilot launch evidence must be an object")
        if set(payload) != {"schema", "ready", "passed", "total", "checks", "journey"}:
            raise ValueError("pilot launch evidence has unsupported fields")
        if payload.get("schema") != GATE_SCHEMA:
            raise ValueError("pilot launch evidence schema is invalid")
        ready = payload.get("ready")
        if not isinstance(ready, bool):
            raise ValueError("pilot launch ready state is invalid")
        passed = _bounded_int(payload.get("passed"), maximum=len(CHECK_IDS))
        total = _bounded_int(payload.get("total"), minimum=len(CHECK_IDS), maximum=len(CHECK_IDS))
        checks = payload.get("checks")
        if not isinstance(checks, list) or len(checks) != len(CHECK_IDS):
            raise ValueError("pilot launch checks are incomplete")
        sanitized_checks: list[dict] = []
        seen: set[str] = set()
        for row in checks:
            if not isinstance(row, dict) or set(row) != {"id", "pass"}:
                raise ValueError("pilot launch check is invalid")
            check_id = str(row.get("id") or "")
            passed_check = row.get("pass")
            if check_id not in CHECK_IDS or check_id in seen or not isinstance(passed_check, bool):
                raise ValueError("pilot launch check is invalid")
            seen.add(check_id)
            sanitized_checks.append({"id": check_id, "pass": passed_check})
        if tuple(row["id"] for row in sanitized_checks) != CHECK_IDS:
            raise ValueError("pilot launch check order is invalid")
        calculated_passed = sum(1 for row in sanitized_checks if row["pass"])
        calculated_ready = calculated_passed == len(CHECK_IDS)
        if passed != calculated_passed or ready != calculated_ready:
            raise ValueError("pilot launch evidence is internally inconsistent")

        journey = payload.get("journey")
        if not isinstance(journey, dict) or set(journey) != {"mode", "pass", "total", "ready"}:
            raise ValueError("pilot journey evidence is invalid")
        mode = str(journey.get("mode") or "").upper()
        if mode not in {"PORTFOLIO", "COMPANY", "NONE"}:
            raise ValueError("pilot journey mode is invalid")
        journey_pass = _bounded_int(journey.get("pass"))
        journey_total = _bounded_int(journey.get("total"))
        journey_ready = journey.get("ready")
        if not isinstance(journey_ready, bool) or journey_pass > journey_total:
            raise ValueError("pilot journey evidence is invalid")
        if journey_ready != (journey_total > 0 and journey_pass == journey_total):
            raise ValueError("pilot journey evidence is internally inconsistent")
        return {
            "ready": ready,
            "passed": passed,
            "total": total,
            "checks": sanitized_checks,
            "journey": {
                "mode": mode,
                "pass": journey_pass,
                "total": journey_total,
                "ready": journey_ready,
            },
        }

    @staticmethod
    def _validate_stored(row: object) -> None:
        if not isinstance(row, dict):
            raise ValueError("invalid pilot receipt row")
        expected = {"schema", "id", "local_date", "recorded_at", "gate"}
        if set(row) != expected or row.get("schema") != RECEIPT_SCHEMA:
            raise ValueError("invalid pilot receipt row")
        if not _RECEIPT_RE.fullmatch(str(row.get("id") or "")):
            raise ValueError("invalid pilot receipt id")
        local_date = str(row.get("local_date") or "")
        if not _DATE_RE.fullmatch(local_date):
            raise ValueError("invalid pilot receipt local date")
        try:
            datetime.fromisoformat(str(row.get("recorded_at") or "").replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("invalid pilot receipt timestamp") from exc
        gate = row.get("gate")
        if not isinstance(gate, dict):
            raise ValueError("invalid pilot receipt gate evidence")
        normalized = PilotDailyReceiptStore._sanitize_gate({"schema": GATE_SCHEMA, **gate})
        if normalized != gate:
            raise ValueError("invalid pilot receipt gate evidence")

    @staticmethod
    def _public(row: dict) -> dict:
        return {
            "schema": RECEIPT_SCHEMA,
            "id": row["id"],
            "local_date": row["local_date"],
            "recorded_at": row["recorded_at"],
            "gate": {
                "ready": bool(row["gate"]["ready"]),
                "passed": int(row["gate"]["passed"]),
                "total": int(row["gate"]["total"]),
                "checks": [dict(item) for item in row["gate"]["checks"]],
                "journey": dict(row["gate"]["journey"]),
            },
        }

    def record(self, payload: object) -> dict:
        if not isinstance(payload, dict) or set(payload) != {"local_date", "gate"}:
            raise ValueError("pilot daily receipt payload has unsupported fields")
        local_date = str(payload.get("local_date") or "")
        if not _DATE_RE.fullmatch(local_date):
            raise ValueError("pilot daily receipt date must be YYYY-MM-DD")
        try:
            datetime.strptime(local_date, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("pilot daily receipt date is invalid") from exc
        gate = self._sanitize_gate(payload.get("gate"))
        now = _now()
        row = {
            "schema": RECEIPT_SCHEMA,
            "id": _receipt_id(now),
            "local_date": local_date,
            "recorded_at": now.isoformat(),
            "gate": gate,
        }
        with self._lock:
            store = self._read()
            store["receipts"].append(row)
            write_json_atomic(self.path, store)
        return self._public(row)

    def list(self, *, limit: int = 90) -> dict:
        requested = _bounded_int(limit, minimum=1, maximum=365)
        with self._lock:
            rows = [self._public(row) for row in self._read()["receipts"]]
        rows.sort(key=lambda row: (row["recorded_at"], row["id"]), reverse=True)
        observed_days = sorted({row["local_date"] for row in rows})
        latest_by_day: dict[str, dict] = {}
        for row in rows:
            latest_by_day.setdefault(row["local_date"], row)
        ready_days = sum(1 for row in latest_by_day.values() if row["gate"]["ready"])
        return {
            "schema": STORE_SCHEMA,
            "receipts": rows[:requested],
            "summary": {
                "receipt_count": len(rows),
                "days_observed": len(observed_days),
                "ready_days": ready_days,
                "attention_days": max(0, len(observed_days) - ready_days),
            },
            "safety": {
                "local_only": True,
                "free_text_stored": False,
                "company_or_contact_identity_stored": False,
                "provider_metadata_stored": False,
                "filesystem_metadata_stored": False,
                "execution_authority": False,
            },
        }


__all__ = [
    "CHECK_IDS",
    "GATE_SCHEMA",
    "PilotDailyReceiptStore",
    "RECEIPT_SCHEMA",
    "STORE_SCHEMA",
]
