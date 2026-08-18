from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path

from .atomic import write_json_atomic
from .paid_media_store import PAID_MEDIA_ID_RE
from .social_store import _now

PLAN_SCHEMA = "binario.marketing.paid-media-plan.v1"
_CAMPAIGN_ID_RE = re.compile(r"^cmp_[a-f0-9]{20}$")
_MEDIA_ID_RE = re.compile(r"^med_[a-f0-9]{20}$")
_ALLOWED_SOURCE_KINDS = {"public_url", "company_media"}
_ALLOWED_DATE_PRESETS = {"today", "yesterday", "last_7d", "last_14d", "last_30d", "this_month", "last_month", "maximum"}


def _timestamp(value: object, field: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone")
    return parsed.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class PaidMediaPlan:
    schema: str
    draft_id: str
    company_id: str
    campaign_id: str | None
    source_kind: str
    company_media_id: str | None
    source_label: str | None
    image_hash: str | None
    currency: str | None
    start_at: str | None
    end_at: str | None
    date_preset: str
    notes: str
    created_at: str
    updated_at: str


class PaidMediaPlanStore:
    """Additive company/product metadata around the certified PaidMediaDraft store.

    This deliberately does not rewrite legacy paid-media JSON. It owns only product-level
    relationships and provider-readback preferences keyed by the existing draft id.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, draft_id: str) -> Path:
        value = str(draft_id or "").strip()
        if not PAID_MEDIA_ID_RE.fullmatch(value):
            raise ValueError("invalid paid media draft id")
        return self.root / f"{value}.json"

    @staticmethod
    def _validated(
        draft_id: str,
        company_id: str,
        payload: dict,
        *,
        created_at: str | None = None,
    ) -> PaidMediaPlan:
        if not isinstance(payload, dict):
            raise ValueError("paid media plan payload must be an object")
        campaign_id = str(payload.get("campaign_id") or "").strip() or None
        if campaign_id and not _CAMPAIGN_ID_RE.fullmatch(campaign_id):
            raise ValueError("invalid campaign id")
        source_kind = str(payload.get("source_kind") or "public_url").strip().lower()
        if source_kind not in _ALLOWED_SOURCE_KINDS:
            raise ValueError("unsupported creative source kind")
        media_id = str(payload.get("company_media_id") or "").strip() or None
        if source_kind == "company_media":
            if not media_id or not _MEDIA_ID_RE.fullmatch(media_id):
                raise ValueError("company_media source requires a valid company_media_id")
        elif media_id:
            raise ValueError("company_media_id is only valid for company_media source")
        currency = str(payload.get("currency") or "").strip().upper() or None
        if currency and (len(currency) != 3 or not currency.isalpha()):
            raise ValueError("currency must be a three-letter code")
        start_at = _timestamp(payload.get("start_at"), "start_at")
        end_at = _timestamp(payload.get("end_at"), "end_at")
        if start_at and end_at and datetime.fromisoformat(end_at) <= datetime.fromisoformat(start_at):
            raise ValueError("end_at must be after start_at")
        date_preset = str(payload.get("date_preset") or "last_7d").strip().lower()
        if date_preset not in _ALLOWED_DATE_PRESETS:
            raise ValueError("unsupported insights date preset")
        notes = str(payload.get("notes") or "").strip()
        if len(notes) > 4000:
            raise ValueError("paid media notes are too long")
        now = _now()
        return PaidMediaPlan(
            schema=PLAN_SCHEMA,
            draft_id=draft_id,
            company_id=str(company_id),
            campaign_id=campaign_id,
            source_kind=source_kind,
            company_media_id=media_id,
            source_label=str(payload.get("source_label") or "").strip() or None,
            image_hash=str(payload.get("image_hash") or "").strip() or None,
            currency=currency,
            start_at=start_at,
            end_at=end_at,
            date_preset=date_preset,
            notes=notes,
            created_at=created_at or now,
            updated_at=now,
        )

    def create(self, draft_id: str, company_id: str, payload: dict) -> PaidMediaPlan:
        with self._lock:
            path = self._path(draft_id)
            if path.exists():
                raise ValueError("paid media plan metadata already exists")
            row = self._validated(draft_id, company_id, payload)
            write_json_atomic(path, asdict(row))
            return row

    def get(self, draft_id: str) -> PaidMediaPlan | None:
        with self._lock:
            path = self._path(draft_id)
            if not path.is_file():
                return None
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema") != PLAN_SCHEMA:
                raise ValueError("invalid paid media plan metadata")
            return PaidMediaPlan(**payload)

    def get_for_company(self, company_id: str, draft_id: str) -> PaidMediaPlan:
        row = self.get(draft_id)
        if row is None or row.company_id != company_id:
            raise KeyError(draft_id)
        return row

    def update_image_hash(self, company_id: str, draft_id: str, image_hash: str) -> PaidMediaPlan:
        value = str(image_hash or "").strip()
        if not value:
            raise ValueError("image_hash is required")
        with self._lock:
            row = self.get_for_company(company_id, draft_id)
            updated = replace(row, image_hash=value, updated_at=_now())
            write_json_atomic(self._path(draft_id), asdict(updated))
            return updated

    def list(self, company_id: str) -> list[PaidMediaPlan]:
        rows = []
        for path in sorted(self.root.glob("pm_*.json")):
            try:
                row = self.get(path.stem)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if row is not None and row.company_id == company_id:
                rows.append(row)
        return sorted(rows, key=lambda row: (row.created_at, row.draft_id))


__all__ = ["PLAN_SCHEMA", "PaidMediaPlan", "PaidMediaPlanStore"]
