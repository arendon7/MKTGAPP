from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import threading
import uuid
from pathlib import Path

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now


UAT_SESSION_ID_RE = re.compile(r"^uat_[0-9a-f]{24}$")
SCENARIO_STATUSES = {"PENDING", "PASS", "FAIL", "BLOCKED", "SKIPPED"}
SESSION_STATUSES = {"IN_PROGRESS", "PASSED", "FAILED", "BLOCKED"}


def _text(value: object, limit: int, *, field: str) -> str | None:
    text = str(value or "").strip()
    if len(text) > limit:
        raise ValueError(f"{field} is too long")
    return text or None


def machine_snapshot() -> dict:
    system = platform.system() or "unknown"
    machine = (platform.machine() or "unknown").lower()
    is_ci = str(os.environ.get("GITHUB_ACTIONS") or "").strip().lower() == "true"
    return {
        "system": system,
        "macos_version": platform.mac_ver()[0] or None,
        "machine": machine,
        "is_ci": is_ci,
        "physical_gate_eligible": system == "Darwin" and machine == "arm64" and not is_ci,
    }


def _digest(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PhysicalUATStore:
    """Durable local evidence for manual physical UAT; never grants a release by itself."""

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
    def _session_id(value: str) -> str:
        session_id = str(value or "").strip()
        if not UAT_SESSION_ID_RE.fullmatch(session_id):
            raise ValueError("invalid UAT session id")
        return session_id

    def _company_root(self, company_id: str) -> Path:
        return self.root / self._company_id(company_id)

    def _path(self, company_id: str, session_id: str) -> Path:
        return self._company_root(company_id) / f"{self._session_id(session_id)}.json"

    @staticmethod
    def _load(path: Path) -> dict:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid physical UAT payload")
        if payload.get("status") not in SESSION_STATUSES:
            raise ValueError("invalid physical UAT session status")
        return payload

    def get(self, company_id: str, session_id: str) -> dict:
        with self._lock:
            path = self._path(company_id, session_id)
            if not path.is_file():
                raise KeyError(session_id)
            row = self._load(path)
        if row.get("company_id") != self._company_id(company_id):
            raise KeyError(session_id)
        return row

    def list(self, company_id: str, *, limit: int = 20) -> list[dict]:
        company = self._company_id(company_id)
        with self._lock:
            rows = [self._load(path) for path in self._company_root(company).glob("uat_*.json")]
        rows = [row for row in rows if row.get("company_id") == company]
        rows.sort(key=lambda row: (row.get("created_at") or "", row.get("id") or ""), reverse=True)
        return rows[: max(1, min(int(limit), 100))]

    def create(
        self,
        company_id: str,
        *,
        scenarios: list[dict],
        build: dict,
        operator: object = None,
        notes: object = None,
    ) -> dict:
        company = self._company_id(company_id)
        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError("physical UAT requires scenarios")
        created_at = _now()
        scenario_rows: list[dict] = []
        seen: set[str] = set()
        for source in scenarios:
            scenario_id = str(source.get("id") or "").strip()
            if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", scenario_id):
                raise ValueError("invalid UAT scenario id")
            if scenario_id in seen:
                raise ValueError("duplicate UAT scenario id")
            seen.add(scenario_id)
            required = scenario_id != "optional-ai"
            scenario_rows.append({
                "id": scenario_id,
                "label": str(source.get("label") or scenario_id).strip()[:200],
                "required": required,
                "status": "PENDING",
                "note": None,
                "updated_at": None,
            })
        row = {
            "schema": "binario.marketing.physical-uat-session.v1",
            "id": f"uat_{uuid.uuid4().hex[:24]}",
            "company_id": company,
            "status": "IN_PROGRESS",
            "operator": _text(operator, 160, field="operator"),
            "notes": _text(notes, 2000, field="notes"),
            "created_at": created_at,
            "updated_at": created_at,
            "finished_at": None,
            "machine": machine_snapshot(),
            "build": dict(build or {}),
            "scenarios": scenario_rows,
            "readiness_at_finish": None,
            "evidence_sha256": None,
            "physical_uat_complete": False,
        }
        with self._lock:
            if any(item.get("status") == "IN_PROGRESS" for item in self.list(company, limit=100)):
                raise ValueError("physical UAT session already in progress for this company")
            write_json_atomic(self._path(company, row["id"]), row)
        return row

    def update_scenario(self, company_id: str, session_id: str, scenario_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("scenario result payload must be an object")
        unknown = set(payload) - {"status", "note"}
        if unknown:
            raise ValueError(f"unsupported UAT scenario fields: {', '.join(sorted(unknown))}")
        status = str(payload.get("status") or "").strip().upper()
        if status not in SCENARIO_STATUSES - {"PENDING"}:
            raise ValueError("invalid UAT scenario status")
        with self._lock:
            row = self.get(company_id, session_id)
            if row.get("status") != "IN_PROGRESS":
                raise ValueError("finished UAT session cannot be modified")
            target = next((item for item in row.get("scenarios") or [] if item.get("id") == scenario_id), None)
            if target is None:
                raise KeyError(scenario_id)
            if status == "SKIPPED" and target.get("required"):
                raise ValueError("required UAT scenario cannot be skipped")
            now = _now()
            target["status"] = status
            target["note"] = _text(payload.get("note"), 2000, field="scenario note")
            target["updated_at"] = now
            row["updated_at"] = now
            write_json_atomic(self._path(company_id, session_id), row)
        return row

    def finish(self, company_id: str, session_id: str, *, readiness: dict) -> dict:
        with self._lock:
            row = self.get(company_id, session_id)
            if row.get("status") != "IN_PROGRESS":
                return row
            scenarios = list(row.get("scenarios") or [])
            required = [item for item in scenarios if item.get("required")]
            pending = [item for item in required if item.get("status") == "PENDING"]
            if pending:
                raise ValueError("required UAT scenarios remain pending")
            statuses = {str(item.get("status") or "") for item in required}
            if "FAIL" in statuses:
                outcome = "FAILED"
            elif "BLOCKED" in statuses:
                outcome = "BLOCKED"
            elif statuses == {"PASS"}:
                outcome = "PASSED"
            else:
                raise ValueError("required UAT scenarios must resolve to PASS, FAIL or BLOCKED")
            now = _now()
            row["status"] = outcome
            row["updated_at"] = now
            row["finished_at"] = now
            row["readiness_at_finish"] = readiness
            row["physical_uat_complete"] = bool(
                outcome == "PASSED" and (row.get("machine") or {}).get("physical_gate_eligible")
            )
            evidence = dict(row)
            evidence["evidence_sha256"] = None
            row["evidence_sha256"] = _digest(evidence)
            write_json_atomic(self._path(company_id, session_id), row)
        return row

    def report(self, company_id: str, session_id: str) -> dict:
        row = self.get(company_id, session_id)
        required = [item for item in row.get("scenarios") or [] if item.get("required")]
        return {
            "schema": "binario.marketing.physical-uat-evidence.v1",
            "session": row,
            "summary": {
                "required": len(required),
                "passed": sum(1 for item in required if item.get("status") == "PASS"),
                "failed": sum(1 for item in required if item.get("status") == "FAIL"),
                "blocked": sum(1 for item in required if item.get("status") == "BLOCKED"),
                "pending": sum(1 for item in required if item.get("status") == "PENDING"),
                "physical_gate_eligible": bool((row.get("machine") or {}).get("physical_gate_eligible")),
                "physical_uat_complete": bool(row.get("physical_uat_complete")),
            },
            "release_authority": False,
        }
