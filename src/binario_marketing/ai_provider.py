from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .ai_credentials import AICredentialStore


class AIProviderError(RuntimeError):
    pass


JSONTransport = Callable[[str, str, dict[str, str], dict[str, Any]], dict[str, Any]]


def _default_transport(method: str, url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=body, method=method.upper(), headers=headers)
    try:
        with urlopen(request, timeout=90) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode("utf-8"))
            message = _provider_error_message(detail) or f"HTTP {exc.code}"
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = f"HTTP {exc.code}"
        raise AIProviderError(f"AI provider request failed: {message}") from None
    except URLError as exc:
        raise AIProviderError(f"AI provider unavailable: {exc.reason}") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise AIProviderError("AI provider returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise AIProviderError("AI provider returned an invalid payload")
    return result


def _provider_error_message(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("type") or "").strip() or None
    if isinstance(error, str):
        return error.strip() or None
    return str(payload.get("message") or "").strip() or None


def _extract_json_text(text: str) -> dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        raise AIProviderError("AI provider returned an empty response")
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        raw = fenced.group(1).strip()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise AIProviderError("AI provider response did not contain JSON") from None
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError as exc:
            raise AIProviderError("AI provider returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise AIProviderError("AI provider output must be a JSON object")
    return payload


def _string(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _strings(value: Any, *, limit: int, item_limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    result = []
    for item in value[:limit]:
        text = _string(item, item_limit)
        if text:
            result.append(text)
    return result


def normalize_copilot_output(payload: dict[str, Any]) -> dict[str, Any]:
    recommendations = []
    for row in payload.get("recommendations") or []:
        if not isinstance(row, dict):
            continue
        priority = _string(row.get("priority"), 12).upper()
        if priority not in {"HIGH", "MEDIUM", "LOW"}:
            priority = "MEDIUM"
        area = _string(row.get("area"), 32).upper()
        if area not in {"STRATEGY", "CAMPAIGN", "CREATIVE", "PAID_MEDIA", "CRM", "CONTENT"}:
            area = "STRATEGY"
        title = _string(row.get("title"), 220)
        next_step = _string(row.get("next_step"), 700)
        if not title or not next_step:
            continue
        recommendations.append({
            "title": title,
            "why": _string(row.get("why"), 1200),
            "priority": priority,
            "area": area,
            "next_step": next_step,
        })
        if len(recommendations) >= 8:
            break

    variants = []
    for row in payload.get("creative_variants") or []:
        if not isinstance(row, dict):
            continue
        copy = _string(row.get("copy"), 5000)
        if not copy:
            continue
        cta = _string(row.get("cta"), 40).upper() or "LEARN_MORE"
        variants.append({
            "label": _string(row.get("label"), 120) or f"Variante {len(variants)+1}",
            "copy": copy,
            "headline": _string(row.get("headline"), 255),
            "cta": cta,
        })
        if len(variants) >= 5:
            break

    brief_raw = payload.get("campaign_brief") if isinstance(payload.get("campaign_brief"), dict) else {}
    campaign_brief = {
        "objective": _string(brief_raw.get("objective"), 500),
        "audience": _string(brief_raw.get("audience"), 1200),
        "proposition": _string(brief_raw.get("proposition"), 1200),
        "channels": _strings(brief_raw.get("channels"), limit=8, item_limit=80),
        "kpis": _strings(brief_raw.get("kpis"), limit=10, item_limit=160),
        "notes": _string(brief_raw.get("notes"), 2000),
    }
    return {
        "summary": _string(payload.get("summary"), 1800),
        "diagnosis": _strings(payload.get("diagnosis"), limit=8, item_limit=1000),
        "recommendations": recommendations,
        "creative_variants": variants,
        "campaign_brief": campaign_brief,
    }


OPENAI_OUTPUT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "diagnosis", "recommendations", "creative_variants", "campaign_brief"],
    "properties": {
        "summary": {"type": "string"},
        "diagnosis": {"type": "array", "items": {"type": "string"}},
        "recommendations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "why", "priority", "area", "next_step"],
                "properties": {
                    "title": {"type": "string"},
                    "why": {"type": "string"},
                    "priority": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
                    "area": {"type": "string", "enum": ["STRATEGY", "CAMPAIGN", "CREATIVE", "PAID_MEDIA", "CRM", "CONTENT"]},
                    "next_step": {"type": "string"},
                },
            },
        },
        "creative_variants": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "copy", "headline", "cta"],
                "properties": {
                    "label": {"type": "string"},
                    "copy": {"type": "string"},
                    "headline": {"type": "string"},
                    "cta": {"type": "string"},
                },
            },
        },
        "campaign_brief": {
            "type": "object",
            "additionalProperties": False,
            "required": ["objective", "audience", "proposition", "channels", "kpis", "notes"],
            "properties": {
                "objective": {"type": "string"},
                "audience": {"type": "string"},
                "proposition": {"type": "string"},
                "channels": {"type": "array", "items": {"type": "string"}},
                "kpis": {"type": "array", "items": {"type": "string"}},
                "notes": {"type": "string"},
            },
        },
    },
}


@dataclass(frozen=True)
class AIGeneration:
    provider: str
    model: str
    output: dict[str, Any]
    provider_meta: dict[str, Any]


class AIProviderClient:
    def __init__(self, credentials: AICredentialStore | None = None, transport: JSONTransport | None = None):
        self.credentials = credentials or AICredentialStore()
        self.transport = transport or _default_transport

    def generate(self, provider: str, model: str, *, system: str, prompt: str) -> AIGeneration:
        provider = str(provider or "").strip().lower()
        model = str(model or "").strip()
        if not model or len(model) > 160:
            raise ValueError("AI model is required")
        if provider == "openai":
            return self._openai(model, system, prompt)
        if provider == "anthropic":
            return self._anthropic(model, system, prompt)
        if provider == "gemini":
            return self._gemini(model, system, prompt)
        if provider == "ollama":
            return self._ollama(model, system, prompt)
        raise ValueError("unsupported AI provider")

    def _openai(self, model: str, system: str, prompt: str) -> AIGeneration:
        key = self.credentials.read("openai")
        if not key:
            raise AIProviderError("OpenAI is not connected")
        payload = self.transport(
            "POST",
            "https://api.openai.com/v1/responses",
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "Accept": "application/json"},
            {
                "model": model,
                "instructions": system,
                "input": prompt,
                "text": {
                    "format": {
                        "type": "json_schema",
                        "name": "binario_marketing_copilot",
                        "schema": OPENAI_OUTPUT_SCHEMA,
                        "strict": True,
                    }
                },
            },
        )
        text = ""
        for item in payload.get("output") or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content") or []:
                if isinstance(content, dict) and content.get("type") == "output_text":
                    text += str(content.get("text") or "")
        if not text and isinstance(payload.get("output_text"), str):
            text = payload["output_text"]
        output = normalize_copilot_output(_extract_json_text(text))
        return AIGeneration("openai", model, output, {"response_id": payload.get("id"), "status": payload.get("status")})

    def _anthropic(self, model: str, system: str, prompt: str) -> AIGeneration:
        key = self.credentials.read("anthropic")
        if not key:
            raise AIProviderError("Anthropic is not connected")
        payload = self.transport(
            "POST",
            "https://api.anthropic.com/v1/messages",
            {
                "x-api-key": key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
                "accept": "application/json",
            },
            {
                "model": model,
                "max_tokens": 3000,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        text = "".join(str(row.get("text") or "") for row in payload.get("content") or [] if isinstance(row, dict) and row.get("type") == "text")
        output = normalize_copilot_output(_extract_json_text(text))
        return AIGeneration("anthropic", model, output, {"response_id": payload.get("id"), "stop_reason": payload.get("stop_reason")})

    def _gemini(self, model: str, system: str, prompt: str) -> AIGeneration:
        key = self.credentials.read("gemini")
        if not key:
            raise AIProviderError("Gemini is not connected")
        payload = self.transport(
            "POST",
            f"https://generativelanguage.googleapis.com/v1beta/models/{quote(model, safe='')}:generateContent",
            {"x-goog-api-key": key, "Content-Type": "application/json", "Accept": "application/json"},
            {
                "system_instruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                "generationConfig": {"responseMimeType": "application/json"},
            },
        )
        candidates = payload.get("candidates") or []
        first = candidates[0] if candidates and isinstance(candidates[0], dict) else {}
        content = first.get("content") if isinstance(first.get("content"), dict) else {}
        text = "".join(str(row.get("text") or "") for row in content.get("parts") or [] if isinstance(row, dict))
        output = normalize_copilot_output(_extract_json_text(text))
        return AIGeneration("gemini", model, output, {"finish_reason": first.get("finishReason")})

    def _ollama(self, model: str, system: str, prompt: str) -> AIGeneration:
        payload = self.transport(
            "POST",
            "http://127.0.0.1:11434/api/chat",
            {"Content-Type": "application/json", "Accept": "application/json"},
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ],
                "format": "json",
                "stream": False,
            },
        )
        message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
        output = normalize_copilot_output(_extract_json_text(str(message.get("content") or "")))
        return AIGeneration("ollama", model, output, {"done_reason": payload.get("done_reason")})


__all__ = [
    "AIProviderClient",
    "AIProviderError",
    "AIGeneration",
    "OPENAI_OUTPUT_SCHEMA",
    "normalize_copilot_output",
]
