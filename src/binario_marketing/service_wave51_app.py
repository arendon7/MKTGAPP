from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .ai_credentials import AI_PROVIDERS, AICredentialError, AICredentialStore
from .ai_provider import AIProviderClient, AIProviderError
from .ai_store import AISessionStore, AISettingsStore, AI_TASKS
from . import service_wave50_app as base


_PROVIDER_NAMES = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "ollama": "Ollama local",
}


class AppRuntime(base.AppRuntime):
    """Wave 51 adds explicit, provider-neutral marketing assistance with no provider tools."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.ai_credentials = AICredentialStore()
        runtime.ai_settings = AISettingsStore(runtime.data_root / "State" / "ai" / "settings")
        runtime.ai_sessions = AISessionStore(runtime.data_root / "State" / "ai" / "sessions")
        runtime.ai_client = AIProviderClient(runtime.ai_credentials)
        return runtime

    def ai_provider_statuses(self) -> list[dict]:
        rows = []
        for provider in AI_PROVIDERS:
            status = self.ai_credentials.status(provider)
            payload = asdict(status)
            payload["name"] = _PROVIDER_NAMES[provider]
            payload["requires_model"] = True
            payload["connection_note"] = (
                "Local; no API key is stored by Binario. The Ollama service/model must already be available on this Mac."
                if provider == "ollama"
                else "Cloud provider; API key resolves from environment or macOS Keychain."
            )
            rows.append(payload)
        return rows

    def connect_ai_provider(self, provider: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("AI provider payload must be an object")
        unknown = set(payload) - {"api_key"}
        if unknown:
            raise ValueError(f"unsupported AI provider fields: {', '.join(sorted(unknown))}")
        status = self.ai_credentials.write(provider, str(payload.get("api_key") or ""))
        self.workspace.registries.timeline.append("ai.provider.connected", {
            "provider": status.provider,
            "source": status.source,
        })
        return next(row for row in self.ai_provider_statuses() if row["provider"] == status.provider)

    def disconnect_ai_provider(self, provider: str) -> dict:
        status = self.ai_credentials.delete(provider)
        self.workspace.registries.timeline.append("ai.provider.disconnected", {
            "provider": status.provider,
            "source": status.source,
        })
        return next(row for row in self.ai_provider_statuses() if row["provider"] == status.provider)

    def ai_settings_payload(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return asdict(self.ai_settings.get(company.id))

    def update_ai_settings(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        row = self.ai_settings.update(company.id, payload)
        self.workspace.registries.timeline.append("ai.settings.updated", {
            "company_id": company.id,
            "provider": row.provider,
            "model": row.model,
            "language": row.language,
        })
        return asdict(row)

    def ai_sessions_payload(self, company_id: str, *, limit: int = 12) -> list[dict]:
        company = self.companies.get(company_id)
        return [asdict(row) for row in self.ai_sessions.list(company.id, limit=limit)]

    def _ai_context(self, company_id: str, *, task: str, campaign_id: str | None, creative_media_id: str | None) -> dict:
        company = self.companies.get(company_id)
        command = self.marketing_command_center(company.id)
        campaigns = []
        for row in self.campaigns.list(company.id):
            campaigns.append({
                "id": row.id,
                "name": row.name,
                "objective": row.objective,
                "status": row.status,
                "channels": list(row.channels),
                "audience_count": len(row.audience_contact_ids),
                "creative_count": len(row.media_ids),
                "publication_count": len(row.publication_ids),
                "start_at": row.start_at,
                "end_at": row.end_at,
                "notes": row.notes,
            })
        creative_rows = self.company_creatives_payload(company.id)
        creative_summary = []
        for row in creative_rows[:30]:
            profile = row.get("creative") or {}
            creative_summary.append({
                "media_id": row["media"]["id"],
                "kind": row["media"]["kind"],
                "stage": row.get("effective_stage"),
                "title": profile.get("title") or row["media"]["original_name"],
                "purpose": profile.get("purpose"),
                "campaign_id": profile.get("campaign_id"),
                "channels": profile.get("channels") or [],
            })

        selected_campaign = None
        if campaign_id:
            row = self.campaigns.get_for_company(company.id, campaign_id)
            selected_campaign = {
                "id": row.id,
                "name": row.name,
                "objective": row.objective,
                "status": row.status,
                "channels": list(row.channels),
                "audience_count": len(row.audience_contact_ids),
                "creative_count": len(row.media_ids),
                "publication_count": len(row.publication_ids),
                "start_at": row.start_at,
                "end_at": row.end_at,
                "notes": row.notes,
            }

        selected_creative = None
        if creative_media_id:
            media = self.company_media.get_for_company(company.id, creative_media_id)
            profile = self.creatives.get(company.id, media.id)
            if profile is None:
                raise ValueError("selected media does not have a Creative Studio brief")
            selected_creative = {
                "media_id": media.id,
                "kind": media.kind,
                "width": media.width,
                "height": media.height,
                "duration": media.duration,
                "title": profile.title,
                "stage": profile.stage,
                "purpose": profile.purpose,
                "campaign_id": profile.campaign_id,
                "channels": list(profile.channels),
                "primary_copy": profile.primary_copy,
                "headline": profile.headline,
                "call_to_action": profile.call_to_action,
                "destination_url": profile.destination_url,
                "notes": profile.notes,
            }

        crm = command.get("crm") or {}
        context = {
            "schema": "binario.marketing.ai-context.v1",
            "privacy": {
                "contact_pii_included": False,
                "media_bytes_included": False,
                "provider_secrets_included": False,
            },
            "company": {"name": company.name},
            "task": task,
            "readiness": {
                "percent": (command.get("readiness") or {}).get("percent"),
                "missing": [row["label"] for row in (command.get("readiness") or {}).get("steps", []) if not row.get("ready")],
            },
            "flow": command.get("flow") or {},
            "attention": command.get("attention") or {},
            "crm": {
                "contacts": crm.get("contacts", 0),
                "opportunities_open": crm.get("opportunities_open", 0),
                "opportunities_won": crm.get("opportunities_won", 0),
                "opportunities_lost": crm.get("opportunities_lost", 0),
                "activities_pending": crm.get("activities_pending", 0),
            },
            "paid_media": command.get("paid_media") or {},
            "publications": command.get("publications") or {},
            "campaigns": campaigns[:20],
            "creatives": creative_summary,
            "selected_campaign": selected_campaign,
            "selected_creative": selected_creative,
        }
        return context

    @staticmethod
    def _ai_prompt(*, task: str, context: dict, instruction: str | None, language: str, brand_voice: str) -> tuple[str, str]:
        task_guidance = {
            "STRATEGY": "Diagnose the current marketing operating state and propose the highest-leverage next actions across strategy, campaigns, content, paid media and CRM.",
            "CAMPAIGN": "Improve the selected campaign. Produce a concrete campaign brief and recommendations grounded only in the supplied campaign/company context.",
            "CREATIVE": "Improve the selected creative. Produce 3-5 meaningfully different copy/headline/CTA variants plus recommendations grounded in its campaign and purpose.",
        }[task]
        system = (
            "You are BINARIO Marketing Copilot, a senior marketing strategist embedded in an operations application. "
            "You may analyze and draft, but you cannot publish, send messages, activate ads, spend budget, call tools or claim that any remote action occurred. "
            "Use only the supplied context; never invent results, customer identities, provider state or performance data. "
            "Return a single JSON object with exactly these top-level keys: summary, diagnosis, recommendations, creative_variants, campaign_brief. "
            "Recommendations must contain title, why, priority (HIGH/MEDIUM/LOW), area (STRATEGY/CAMPAIGN/CREATIVE/PAID_MEDIA/CRM/CONTENT), next_step. "
            "Creative variants contain label, copy, headline, cta. Campaign brief contains objective, audience, proposition, channels, kpis, notes. "
            f"Write user-facing content in language '{language}'."
        )
        if brand_voice.strip():
            system += f" Respect this company voice guidance: {brand_voice.strip()}"
        prompt = task_guidance + "\n\nSanitized company context:\n" + json.dumps(context, ensure_ascii=False, sort_keys=True, indent=2)
        if instruction:
            prompt += "\n\nAdditional user instruction:\n" + instruction
        return system, prompt

    def generate_ai_copilot(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("AI generation payload must be an object")
        allowed = {"task", "campaign_id", "creative_media_id", "instruction"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported AI generation fields: {', '.join(sorted(unknown))}")
        company = self.companies.get(company_id)
        settings = self.ai_settings.get(company.id)
        provider = str(settings.provider or "").strip().lower()
        model = str(settings.model or "").strip()
        if not provider or not model:
            raise ValueError("configure an AI provider and model for this company first")
        status = self.ai_credentials.status(provider)
        if provider != "ollama" and not status.configured:
            raise AICredentialError(f"{provider} is not connected")
        task = str(payload.get("task") or "STRATEGY").strip().upper()
        if task not in AI_TASKS:
            raise ValueError("unsupported AI task")
        campaign_id = str(payload.get("campaign_id") or "").strip() or None
        creative_media_id = str(payload.get("creative_media_id") or "").strip() or None
        if task == "CAMPAIGN" and not campaign_id:
            raise ValueError("campaign task requires campaign_id")
        if task == "CREATIVE" and not creative_media_id:
            raise ValueError("creative task requires creative_media_id")
        instruction = str(payload.get("instruction") or "").strip() or None
        if instruction and len(instruction) > 4000:
            raise ValueError("AI instruction is too long")
        context = self._ai_context(
            company.id,
            task=task,
            campaign_id=campaign_id,
            creative_media_id=creative_media_id,
        )
        canonical = json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        context_sha256 = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        system, prompt = self._ai_prompt(
            task=task,
            context=context,
            instruction=instruction,
            language=settings.language,
            brand_voice=settings.brand_voice,
        )
        generation = self.ai_client.generate(provider, model, system=system, prompt=prompt)
        session = self.ai_sessions.create(
            company.id,
            provider=generation.provider,
            model=generation.model,
            task=task,
            campaign_id=campaign_id,
            creative_media_id=creative_media_id,
            instruction=instruction,
            context_sha256=context_sha256,
            context=context,
            output=generation.output,
            provider_meta=generation.provider_meta,
        )
        self.workspace.registries.timeline.append("ai.copilot.generated", {
            "company_id": company.id,
            "session_id": session.id,
            "provider": generation.provider,
            "model": generation.model,
            "task": task,
            "campaign_id": campaign_id,
            "creative_media_id": creative_media_id,
            "context_sha256": context_sha256,
        })
        return asdict(session)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _wave51_error(self, exc: Exception) -> None:
        if isinstance(exc, (AIProviderError, AICredentialError)):
            self._error(HTTPStatus.BAD_GATEWAY if isinstance(exc, AIProviderError) else HTTPStatus.CONFLICT, str(exc))
            return
        self._wave47_error(exc)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/ai-copilot.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "ai", "providers"]:
                self._json(self.server.runtime.ai_provider_statuses())
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "settings"]:
                self._json(self.server.runtime.ai_settings_payload(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "sessions"]:
                query = parse_qs(urlparse(self.path).query)
                limit = int((query.get("limit") or [12])[0])
                self._json(self.server.runtime.ai_sessions_payload(parts[2], limit=limit))
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_GET()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "settings"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.update_ai_settings(parts[2], self._body())
                self._json(result)
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_PATCH()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:3] == ["api", "ai", "providers"] and parts[4] == "connection":
                with self.server.mutation_lock:
                    result = self.server.runtime.connect_ai_provider(parts[3], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "generate"]:
                # Generation is only user-triggered. The provider receives sanitized local context.
                result = self.server.runtime.generate_ai_copilot(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:3] == ["api", "ai", "providers"] and parts[4] == "connection":
                with self.server.mutation_lock:
                    result = self.server.runtime.disconnect_ai_provider(parts[3])
                self._json(result)
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_DELETE()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App: {url}")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
