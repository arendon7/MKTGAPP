from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .ai_credentials import AI_PROVIDERS
from .atomic import write_json_atomic
from .company_store import COMPANY_ID_RE
from .social_store import _now

AI_SETTINGS_SCHEMA = "binario.marketing.ai-settings.v1"
AI_SESSION_SCHEMA = "binario.marketing.ai-session.v1"
AI_SESSION_ID_RE = re.compile(r"^ai_[0-9a-f]{24}$")
AI_TASKS = ("STRATEGY", "CAMPAIGN", "CREATIVE")


def _company(value: str) -> str:
    company_id = str(value or "").strip()
    if not COMPANY_ID_RE.fullmatch(company_id):
        raise ValueError("invalid company id")
    return company_id


def _text(value: Any, limit: int, *, field: str, required: bool = False) -> str | None:
    result = str(value or "").strip()
    if required and not result:
        raise ValueError(f"{field} is required")
    if len(result) > limit:
        raise ValueError(f"{field} is too long")
    return result or None


@dataclass(frozen=True)
class AISettings:
    schema: str
    company_id: str
    provider: str | None
    model: str | None
    language: str
    brand_voice: str
    updated_at: str


@dataclass(frozen=True)
class AISession:
    schema: str
    id: str
    company_id: str
    provider: str
    model: str
    task: str
    campaign_id: str | None
    creative_media_id: str | None
    instruction: str | None
    context_sha256: str
    context: dict[str, Any]
    output: dict[str, Any]
    provider_meta: dict[str, Any]
    created_at: str


class AISettingsStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _path(self, company_id: str) -> Path:
        return self.root / f"{_company(company_id)}.json"

    def get(self, company_id: str) -> AISettings:
        company = _company(company_id)
        path = self._path(company)
        with self._lock:
            if not path.is_file():
                return AISettings(AI_SETTINGS_SCHEMA, company, None, None, "es", "", _now())
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict) or payload.get("schema") != AI_SETTINGS_SCHEMA:
                raise ValueError("invalid AI settings")
            return AISettings(**payload)

    def update(self, company_id: str, payload: dict) -> AISettings:
        if not isinstance(payload, dict):
            raise ValueError("AI settings payload must be an object")
        allowed = {"provider", "model", "language", "brand_voice"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported AI settings fields: {', '.join(sorted(unknown))}")
        company = _company(company_id)
        current = self.get(company)
        provider = current.provider
        if "provider" in payload:
            provider = str(payload.get("provider") or "").strip().lower() or None
            if provider and provider not in AI_PROVIDERS:
                raise ValueError("unsupported AI provider")
        model = current.model
        if "model" in payload:
            model = _text(payload.get("model"), 160, field="AI model")
        language = current.language
        if "language" in payload:
            language = _text(payload.get("language"), 20, field="language", required=True) or "es"
        brand_voice = current.brand_voice
        if "brand_voice" in payload:
            brand_voice = _text(payload.get("brand_voice"), 6000, field="brand_voice") or ""
        row = AISettings(AI_SETTINGS_SCHEMA, company, provider, model, language, brand_voice, _now())
        with self._lock:
            write_json_atomic(self._path(company), asdict(row))
        return row


class AISessionStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _folder(self, company_id: str) -> Path:
        folder = self.root / _company(company_id)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def create(
        self,
        company_id: str,
        *,
        provider: str,
        model: str,
        task: str,
        campaign_id: str | None,
        creative_media_id: str | None,
        instruction: str | None,
        context_sha256: str,
        context: dict[str, Any],
        output: dict[str, Any],
        provider_meta: dict[str, Any] | None = None,
    ) -> AISession:
        company = _company(company_id)
        provider_value = str(provider or "").strip().lower()
        if provider_value not in AI_PROVIDERS:
            raise ValueError("unsupported AI provider")
        model_value = _text(model, 160, field="AI model", required=True) or ""
        task_value = str(task or "").strip().upper()
        if task_value not in AI_TASKS:
            raise ValueError("unsupported AI task")
        digest = str(context_sha256 or "").strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid AI context sha256")
        if not isinstance(context, dict) or not isinstance(output, dict):
            raise ValueError("AI context/output must be objects")
        meta = dict(provider_meta or {})
        for key in list(meta):
            if str(key).lower() in {"api_key", "access_token", "authorization", "token", "secret"}:
                meta.pop(key, None)
        row = AISession(
            schema=AI_SESSION_SCHEMA,
            id=f"ai_{uuid.uuid4().hex[:24]}",
            company_id=company,
            provider=provider_value,
            model=model_value,
            task=task_value,
            campaign_id=str(campaign_id or "").strip() or None,
            creative_media_id=str(creative_media_id or "").strip() or None,
            instruction=_text(instruction, 4000, field="instruction"),
            context_sha256=digest,
            context=context,
            output=output,
            provider_meta=meta,
            created_at=_now(),
        )
        folder = self._folder(company)
        with self._lock:
            write_json_atomic(folder / f"{row.id}.json", asdict(row))
        return row

    def list(self, company_id: str, *, limit: int = 20) -> list[AISession]:
        company = _company(company_id)
        safe_limit = max(1, min(100, int(limit)))
        rows: list[AISession] = []
        with self._lock:
            for path in self._folder(company).glob("ai_*.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(payload, dict) or payload.get("schema") != AI_SESSION_SCHEMA:
                        continue
                    row = AISession(**payload)
                    if row.company_id == company:
                        rows.append(row)
                except (OSError, ValueError, TypeError, json.JSONDecodeError):
                    continue
        return sorted(rows, key=lambda row: (row.created_at, row.id), reverse=True)[:safe_limit]


__all__ = [
    "AI_SETTINGS_SCHEMA",
    "AI_SESSION_SCHEMA",
    "AI_TASKS",
    "AISession",
    "AISessionStore",
    "AISettings",
    "AISettingsStore",
]
