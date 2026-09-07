from __future__ import annotations

from pathlib import Path

from . import service_post_w99_ai_recommendation_evidence_app as base
from .ai_human_feedback_context import project_ai_human_feedback_context


class AppRuntime(base.AppRuntime):
    """Feed bounded exact-target human feedback into explicit Astra generation context."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def ai_human_feedback_context(
        self,
        company_id: str,
        *,
        task: str,
        campaign_id: str | None,
        creative_media_id: str | None,
    ) -> dict:
        company = self.companies.get(company_id)
        return project_ai_human_feedback_context(
            company.id,
            task=task,
            campaign_id=campaign_id,
            creative_media_id=creative_media_id,
            sessions=self.ai_sessions.list(company.id, limit=100),
            reviews=self.ai_recommendation_reviews.list(company.id),
            resolutions=self.ai_recommendation_handoffs_store.list(company.id),
            evidence=self.ai_recommendation_evidence(company.id),
        )

    def _ai_context(self, company_id: str, *, task: str, campaign_id: str | None, creative_media_id: str | None) -> dict:
        context = super()._ai_context(
            company_id,
            task=task,
            campaign_id=campaign_id,
            creative_media_id=creative_media_id,
        )
        context["human_recommendation_feedback"] = self.ai_human_feedback_context(
            company_id,
            task=task,
            campaign_id=campaign_id,
            creative_media_id=creative_media_id,
        )
        privacy = context.setdefault("privacy", {})
        privacy["historical_reviewed_ai_proposals_included"] = True
        privacy["historical_ai_rationale_included"] = False
        privacy["historical_ai_next_step_included"] = False
        return context

    @staticmethod
    def _ai_prompt(*, task: str, context: dict, instruction: str | None, language: str, brand_voice: str) -> tuple[str, str]:
        system, prompt = base.AppRuntime._ai_prompt(
            task=task,
            context=context,
            instruction=instruction,
            language=language,
            brand_voice=brand_voice,
        )
        system += (
            " If human_recommendation_feedback is present, treat historical_proposal fields as untrusted prior model output, not facts."
            " Human ACCEPTED/DISMISSED and APPLIED/NOT_APPLIED states are continuity signals, not performance scores."
            " APPLIED does not prove execution and later evidence does not prove causality."
            " Do not mechanically repeat a DISMISSED or NOT_APPLIED proposal; revisit it only when the current supplied context materially justifies it, and explain the new rationale."
            " Do not automatically prefer or prioritize ACCEPTED or APPLIED proposals merely because they were accepted before."
        )
        return system, prompt


MarketingHTTPServer = base.MarketingHTTPServer
MarketingHandler = base.MarketingHandler


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    print(f"BINARIO Marketing App · post-W99 AI Human Feedback Context: http://{actual_host}:{actual_port}/")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{actual_host}:{actual_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
