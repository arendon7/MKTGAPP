from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_ai_recommendation_review_app as base
from .ai_recommendation_handoff import (
    RecommendationHandoffConflict,
    RecommendationHandoffStore,
    extend_action_center,
    project_recommendation_handoffs,
)


_HANDOFF_RESULT_SCHEMA = "binario.marketing.ai-recommendation-handoff-result.v1"


class AppRuntime(base.AppRuntime):
    """Turn accepted AI recommendations into explicit local owner handoffs, never execution."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.ai_recommendation_handoffs_store = RecommendationHandoffStore(
            runtime.data_root / "State" / "ai" / "recommendation_handoffs"
        )
        return runtime

    def ai_recommendation_handoffs(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return project_recommendation_handoffs(
            company.id,
            sessions=self.ai_sessions.list(company.id, limit=100),
            reviews=self.ai_recommendation_reviews.list(company.id),
            resolutions=self.ai_recommendation_handoffs_store.list(company.id),
        )

    def action_center(self, company_id: str) -> dict:
        return extend_action_center(
            super().action_center(company_id),
            self.ai_recommendation_handoffs(company_id),
        )

    def resolve_ai_recommendation_handoff(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("AI recommendation handoff payload must be an object")
        unknown = set(payload) - {"recommendation_id", "outcome"}
        if unknown:
            raise ValueError(f"unsupported AI recommendation handoff fields: {', '.join(sorted(unknown))}")
        recommendation_id = str(payload.get("recommendation_id") or "").strip()
        outcome = str(payload.get("outcome") or "").strip().upper()
        if outcome not in {"APPLIED", "NOT_APPLIED"}:
            raise ValueError("AI recommendation handoff outcome must be APPLIED or NOT_APPLIED")

        existing = self.ai_recommendation_handoffs_store.get(company.id, recommendation_id)
        if existing is not None:
            if existing.outcome != outcome:
                raise RecommendationHandoffConflict("AI recommendation handoff was already resolved with another outcome")
            return {
                "schema": _HANDOFF_RESULT_SCHEMA,
                "resolution": asdict(existing),
                "reused": True,
                "projection": self.ai_recommendation_handoffs(company.id),
                "safety": {
                    "provider_call_performed": False,
                    "ai_generation_performed": False,
                    "business_execution_performed": False,
                    "automatic": False,
                },
            }

        projection = self.ai_recommendation_handoffs(company.id)
        matches = [row for row in projection.get("handoffs") or [] if row.get("recommendation_id") == recommendation_id]
        if len(matches) != 1:
            raise RecommendationHandoffConflict(
                "AI recommendation handoff is no longer current or has no exact structured owner"
            )
        source = matches[0]
        route = source.get("route") or {}
        if route.get("state") != "OWNER_RESOLVED":
            raise RecommendationHandoffConflict("AI recommendation has no exact structured owner")
        row = self.ai_recommendation_handoffs_store.record(
            company.id,
            recommendation_id=recommendation_id,
            session_id=str(source.get("session_id") or ""),
            digest=str(source.get("recommendation_sha256") or ""),
            outcome=outcome,
        )
        self.workspace.registries.timeline.append("ai.recommendation.handoff.resolved", {
            "company_id": company.id,
            "recommendation_id": row.recommendation_id,
            "session_id": row.session_id,
            "outcome": row.outcome,
            "owner_view": route.get("view"),
            "provider_call_performed": False,
            "business_execution_performed": False,
            "automatic": False,
            "recommendation_content_logged": False,
        })
        return {
            "schema": _HANDOFF_RESULT_SCHEMA,
            "resolution": asdict(row),
            "reused": False,
            "projection": self.ai_recommendation_handoffs(company.id),
            "safety": {
                "provider_call_performed": False,
                "ai_generation_performed": False,
                "business_execution_performed": False,
                "automatic": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose local handoff projection and explicit resolution only."""

    def _static(self, path: str) -> None:
        if path == "/ai-recommendation-review.js":
            target = self.server.runtime.repo_root / "web" / "ai-recommendation-review.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99AIRecommendationHandoff(){
  if(document.querySelector('script[data-post-w99-ai-recommendation-handoff]'))return;
  const script=document.createElement('script');
  script.src='/ai-recommendation-handoff.js';
  script.defer=true;
  script.dataset.postW99AiRecommendationHandoff='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/ai-recommendation-handoff.js":
            target = self.server.runtime.repo_root / "web" / "ai-recommendation-handoff.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/ai-recommendation-handoff.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "recommendation-handoffs"]:
                self._json(self.server.runtime.ai_recommendation_handoffs(parts[2]))
                return
        except Exception as exc:
            if isinstance(exc, KeyError):
                self._error(HTTPStatus.NOT_FOUND, "company not found")
            elif isinstance(exc, (ValueError, TypeError)):
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            else:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "recommendation-handoffs"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.resolve_ai_recommendation_handoff(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
        except Exception as exc:
            if isinstance(exc, RecommendationHandoffConflict):
                self._error(HTTPStatus.CONFLICT, str(exc))
            elif isinstance(exc, KeyError):
                self._error(HTTPStatus.NOT_FOUND, "company not found")
            elif isinstance(exc, (ValueError, TypeError)):
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            else:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")
            return
        super().do_POST()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    print(f"BINARIO Marketing App · post-W99 AI Accepted Owner Handoff: http://{actual_host}:{actual_port}/")
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
