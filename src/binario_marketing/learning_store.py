from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _assert_secret_free, _now

LEARNING_SCHEMA = "binario.marketing.learning-snapshot.v1"
DECISION_SCHEMA = "binario.marketing.learning-decision.v1"
SNAPSHOT_ID_RE = re.compile(r"^learning_[0-9a-f]{24}$")
DECISION_ID_RE = re.compile(r"^decision_[0-9a-f]{24}$")
DECISION_ACTIONS = ("SCALE", "ITERATE", "HOLD", "RETIRE")
DECISION_ENTITY_KINDS = ("CAMPAIGN", "CREATIVE")
DATE_PRESETS = ("today", "yesterday", "last_7d", "last_14d", "last_30d", "this_month", "last_month", "maximum")


def _company(value: object) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def _text(value: object, limit: int, *, field: str, required: bool = False) -> str | None:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} is too long")
    return text or None


def _safe_payload(value: Any, *, field: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    _assert_secret_free(value, field)
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > 2_000_000:
        raise ValueError(f"{field} is too large")
    return value


@dataclass(frozen=True)
class LearningSnapshot:
    schema: str
    id: str
    company_id: str
    date_preset: str
    social: dict
    paid_media: dict
    crm: dict
    coverage: dict
    created_at: str


@dataclass(frozen=True)
class LearningDecision:
    schema: str
    id: str
    company_id: str
    entity_kind: str
    entity_id: str
    action: str
    rationale: str
    snapshot_id: str | None
    created_at: str


class LearningStore:
    """Durable evidence snapshots and explicit local marketing decisions.

    The store receives already-sanitized evidence. It never performs provider calls and
    never executes the decision represented by a LearningDecision.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.snapshots_root = self.root / "snapshots"
        self.decisions_root = self.root / "decisions"
        self.snapshots_root.mkdir(parents=True, exist_ok=True)
        self.decisions_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _path(root: Path, row_id: str, pattern: re.Pattern[str]) -> Path:
        if not pattern.fullmatch(str(row_id or "")):
            raise ValueError("invalid learning record id")
        return root / f"{row_id}.json"

    @staticmethod
    def _load(path: Path, cls):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid learning payload")
        _assert_secret_free(payload)
        return cls(**payload)

    def create_snapshot(self, company_id: str, payload: dict) -> LearningSnapshot:
        company = _company(company_id)
        if not isinstance(payload, dict):
            raise ValueError("learning snapshot payload must be an object")
        allowed = {"date_preset", "social", "paid_media", "crm", "coverage"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported learning snapshot fields: {', '.join(sorted(unknown))}")
        preset = str(payload.get("date_preset") or "last_7d").strip().lower()
        if preset not in DATE_PRESETS:
            raise ValueError("unsupported learning date preset")
        row = LearningSnapshot(
            schema=LEARNING_SCHEMA,
            id=f"learning_{uuid.uuid4().hex[:24]}",
            company_id=company,
            date_preset=preset,
            social=_safe_payload(payload.get("social") or {}, field="social evidence"),
            paid_media=_safe_payload(payload.get("paid_media") or {}, field="paid-media evidence"),
            crm=_safe_payload(payload.get("crm") or {}, field="crm evidence"),
            coverage=_safe_payload(payload.get("coverage") or {}, field="coverage evidence"),
            created_at=_now(),
        )
        with self._lock:
            write_json_atomic(self._path(self.snapshots_root, row.id, SNAPSHOT_ID_RE), asdict(row))
        return row

    def get_snapshot(self, company_id: str, snapshot_id: str) -> LearningSnapshot:
        company = _company(company_id)
        with self._lock:
            path = self._path(self.snapshots_root, snapshot_id, SNAPSHOT_ID_RE)
            if not path.is_file():
                raise KeyError(snapshot_id)
            row = self._load(path, LearningSnapshot)
        if row.company_id != company:
            raise KeyError(snapshot_id)
        return row

    def list_snapshots(self, company_id: str, *, limit: int = 20) -> list[LearningSnapshot]:
        company = _company(company_id)
        if limit < 1 or limit > 100:
            raise ValueError("learning snapshot limit must be between 1 and 100")
        with self._lock:
            rows = [self._load(path, LearningSnapshot) for path in self.snapshots_root.glob("learning_*.json")]
        rows = [row for row in rows if row.company_id == company]
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        return rows[:limit]

    def latest_snapshot(self, company_id: str) -> LearningSnapshot | None:
        rows = self.list_snapshots(company_id, limit=1)
        return rows[0] if rows else None

    def create_decision(self, company_id: str, payload: dict) -> LearningDecision:
        company = _company(company_id)
        if not isinstance(payload, dict):
            raise ValueError("learning decision payload must be an object")
        allowed = {"entity_kind", "entity_id", "action", "rationale", "snapshot_id"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported learning decision fields: {', '.join(sorted(unknown))}")
        entity_kind = str(payload.get("entity_kind") or "").strip().upper()
        if entity_kind not in DECISION_ENTITY_KINDS:
            raise ValueError("unsupported learning decision entity")
        entity_id = _text(payload.get("entity_id"), 96, field="entity_id", required=True) or ""
        if entity_kind == "CAMPAIGN" and not re.fullmatch(r"campaign_[0-9a-f]{24}", entity_id):
            raise ValueError("invalid campaign decision entity")
        if entity_kind == "CREATIVE" and not re.fullmatch(r"media_[0-9a-f]{24}", entity_id):
            raise ValueError("invalid creative decision entity")
        action = str(payload.get("action") or "").strip().upper()
        if action not in DECISION_ACTIONS:
            raise ValueError("unsupported learning decision action")
        rationale = _text(payload.get("rationale"), 4000, field="rationale", required=True) or ""
        snapshot_id = _text(payload.get("snapshot_id"), 64, field="snapshot_id")
        if snapshot_id:
            self.get_snapshot(company, snapshot_id)
        row = LearningDecision(
            schema=DECISION_SCHEMA,
            id=f"decision_{uuid.uuid4().hex[:24]}",
            company_id=company,
            entity_kind=entity_kind,
            entity_id=entity_id,
            action=action,
            rationale=rationale,
            snapshot_id=snapshot_id,
            created_at=_now(),
        )
        with self._lock:
            write_json_atomic(self._path(self.decisions_root, row.id, DECISION_ID_RE), asdict(row))
        return row

    def list_decisions(self, company_id: str, *, limit: int = 50) -> list[LearningDecision]:
        company = _company(company_id)
        if limit < 1 or limit > 200:
            raise ValueError("learning decision limit must be between 1 and 200")
        with self._lock:
            rows = [self._load(path, LearningDecision) for path in self.decisions_root.glob("decision_*.json")]
        rows = [row for row in rows if row.company_id == company]
        rows.sort(key=lambda row: (row.created_at, row.id), reverse=True)
        return rows[:limit]


__all__ = [
    "DATE_PRESETS",
    "DECISION_ACTIONS",
    "DECISION_ENTITY_KINDS",
    "DECISION_SCHEMA",
    "LEARNING_SCHEMA",
    "LearningDecision",
    "LearningSnapshot",
    "LearningStore",
]
