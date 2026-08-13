from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic import write_json_atomic
from .meta_ads import LinkCreativeSpec, PausedAdSetSpec


PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
STATUSES = {"DRAFT", "REMOTE_PAUSED", "CANCELLED"}
_REMOTE_FIELDS = ("campaign_id", "adset_id", "creative_id", "ad_id")
_SECRET_KEYS = {"access_token", "token", "client_secret", "app_secret", "password", "authorization"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assert_secret_free(value: Any, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).strip().lower() in _SECRET_KEYS:
                raise ValueError(f"credentials must not be persisted in {path}")
            _assert_secret_free(child, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _assert_secret_free(child, f"{path}[{index}]")


@dataclass(frozen=True)
class PaidMediaDraft:
    id: str
    project_id: str
    ad_account_id: str
    campaign_name: str
    campaign_objective: str
    special_ad_categories: list[str]
    adset_name: str
    daily_budget: int
    optimization_goal: str
    targeting: dict[str, Any]
    page_id: str
    instagram_actor_id: str | None
    creative_name: str
    message: str
    link_url: str
    picture_url: str
    call_to_action: str
    ad_name: str
    status: str
    campaign_id: str | None
    adset_id: str | None
    creative_id: str | None
    ad_id: str | None
    created_at: str
    updated_at: str


class PaidMediaStore:
    """Durable local paid-media plans. No provider credentials are accepted or persisted."""

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, draft_id: str) -> Path:
        if not re.fullmatch(r"[0-9a-f]{32}", draft_id):
            raise ValueError("invalid paid media draft id")
        return self.root / f"{draft_id}.json"

    def _load(self, path: Path) -> PaidMediaDraft:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid paid media draft payload")
        _assert_secret_free(payload)
        return PaidMediaDraft(**payload)

    def get(self, draft_id: str) -> PaidMediaDraft:
        with self._lock:
            path = self._path(draft_id)
            if not path.is_file():
                raise KeyError(draft_id)
            return self._load(path)

    def list(self, project_id: str | None = None) -> list[PaidMediaDraft]:
        if project_id is not None and not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("invalid project id")
        with self._lock:
            rows = [self._load(path) for path in self.root.glob("*.json")]
        if project_id is not None:
            rows = [row for row in rows if row.project_id == project_id]
        return sorted(rows, key=lambda row: (row.created_at, row.id))

    def create(self, project_id: str, payload: dict) -> PaidMediaDraft:
        if not PROJECT_ID_RE.fullmatch(project_id):
            raise ValueError("invalid project id")
        if not isinstance(payload, dict):
            raise ValueError("paid media payload must be an object")
        _assert_secret_free(payload)
        categories = payload.get("special_ad_categories") or []
        if not isinstance(categories, list) or any(not isinstance(item, str) for item in categories):
            raise ValueError("special_ad_categories must be a list of strings")
        adset = PausedAdSetSpec(
            ad_account_id=str(payload.get("ad_account_id") or ""),
            campaign_id="draft-campaign",
            name=str(payload.get("adset_name") or ""),
            daily_budget=payload.get("daily_budget"),
            optimization_goal=str(payload.get("optimization_goal") or ""),
            targeting=payload.get("targeting") or {},
        )
        adset.validate()
        creative = LinkCreativeSpec(
            ad_account_id=adset.ad_account_id,
            page_id=str(payload.get("page_id") or ""),
            instagram_actor_id=(str(payload.get("instagram_actor_id")).strip() if payload.get("instagram_actor_id") else None),
            name=str(payload.get("creative_name") or ""),
            message=str(payload.get("message") or ""),
            link_url=str(payload.get("link_url") or ""),
            picture_url=str(payload.get("picture_url") or ""),
            call_to_action=str(payload.get("call_to_action") or "LEARN_MORE"),
        )
        creative.validate()
        campaign_name = str(payload.get("campaign_name") or "").strip()
        objective = str(payload.get("campaign_objective") or "").strip().upper()
        ad_name = str(payload.get("ad_name") or "").strip()
        if not campaign_name or len(campaign_name) > 255:
            raise ValueError("campaign_name is required")
        if not objective.startswith("OUTCOME_") or len(objective) > 64:
            raise ValueError("campaign_objective must use OUTCOME_* naming")
        if not ad_name or len(ad_name) > 255:
            raise ValueError("ad_name is required")
        now = _now()
        row = PaidMediaDraft(
            id=uuid.uuid4().hex,
            project_id=project_id,
            ad_account_id=adset.ad_account_id,
            campaign_name=campaign_name,
            campaign_objective=objective,
            special_ad_categories=[item.strip().upper() for item in categories if item.strip()],
            adset_name=adset.name.strip(),
            daily_budget=adset.daily_budget,
            optimization_goal=adset.optimization_goal.strip().upper(),
            targeting=adset.targeting,
            page_id=creative.page_id.strip(),
            instagram_actor_id=creative.instagram_actor_id,
            creative_name=creative.name.strip(),
            message=creative.message.strip(),
            link_url=creative.link_url.strip(),
            picture_url=creative.picture_url.strip(),
            call_to_action=creative.call_to_action.strip().upper(),
            ad_name=ad_name,
            status="DRAFT",
            campaign_id=None,
            adset_id=None,
            creative_id=None,
            ad_id=None,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            write_json_atomic(self._path(row.id), asdict(row))
        return row

    def checkpoint_remote(self, draft_id: str, field: str, remote_id: str) -> PaidMediaDraft:
        if field not in _REMOTE_FIELDS:
            raise ValueError("unsupported remote checkpoint field")
        value = str(remote_id or "").strip()
        if not value or len(value) > 128:
            raise ValueError("remote Meta object id is required")
        with self._lock:
            row = self.get(draft_id)
            if row.status != "DRAFT":
                raise ValueError("only DRAFT paid media plans can receive remote checkpoints")
            position = _REMOTE_FIELDS.index(field)
            for previous in _REMOTE_FIELDS[:position]:
                if not getattr(row, previous):
                    raise ValueError(f"remote checkpoint order requires {previous} first")
            existing = getattr(row, field)
            if existing:
                if existing != value:
                    raise ValueError(f"remote checkpoint {field} is immutable once recorded")
                return row
            updated = replace(row, **{field: value, "updated_at": _now()})
            write_json_atomic(self._path(updated.id), asdict(updated))
            return updated

    def mark_remote_paused(self, draft_id: str) -> PaidMediaDraft:
        with self._lock:
            row = self.get(draft_id)
            if row.status != "DRAFT":
                raise ValueError("only DRAFT paid media plans can be marked remote")
            if any(not getattr(row, field) for field in _REMOTE_FIELDS):
                raise ValueError("all remote Meta object ids must be checkpointed first")
            updated = replace(row, status="REMOTE_PAUSED", updated_at=_now())
            write_json_atomic(self._path(updated.id), asdict(updated))
            return updated

    def cancel(self, draft_id: str) -> PaidMediaDraft:
        with self._lock:
            row = self.get(draft_id)
            if row.status != "DRAFT":
                raise ValueError("only local DRAFT plans can be cancelled")
            if any(getattr(row, field) for field in _REMOTE_FIELDS):
                raise ValueError("draft has remote Meta objects; review them before cancelling locally")
            updated = replace(row, status="CANCELLED", updated_at=_now())
            write_json_atomic(self._path(updated.id), asdict(updated))
            return updated
