from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_results_freshness_guard_app as base
from .ai_recommendation_review import (
    RecommendationReviewConflict,
    RecommendationReviewStore,
    current_recommendations,
    extend_action_center,
    project_recommendation_review,
)


_REVIEW_RESULT_SCHEMA = "binario.marketing.ai-recommendation-review-result.v1"


class AppRuntime(base.AppRuntime):
    """Expose human review of already-generated AI recommendations without execution authority."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.ai_recommendation_reviews = RecommendationReviewStore(
            runtime.data_root / "State" / "ai" / "recommendation_reviews"
        )
        return runtime

    def ai_recommendation_review(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return project_recommendation_review(
            company.id,
            sessions=self.ai_sessions.list(company.id, limit=100),
            reviews=self.ai_recommendation_reviews.list(company.id),
        )

    def action_center(self, company_id: str) -> dict:
        return extend_action_center(
            super().action_center(company_id),
            self.ai_recommendation_review(company_id),
        )

    def review_ai_recommendation(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("AI recommendation review payload must be an object")
        unknown = set(payload) - {"recommendation_id", "decision"}
        if unknown:
            raise ValueError(f"unsupported AI recommendation review fields: {', '.join(sorted(unknown))}")
        recommendation_id = str(payload.get("recommendation_id") or "").strip()
        decision = str(payload.get("decision") or "").strip().upper()
        if decision not in {"ACCEPTED", "DISMISSED"}:
            raise ValueError("AI recommendation review decision must be ACCEPTED or DISMISSED")

        existing = self.ai_recommendation_reviews.get(company.id, recommendation_id)
        if existing is not None:
            if existing.decision != decision:
                raise RecommendationReviewConflict("AI recommendation was already reviewed with another decision")
            projection = self.ai_recommendation_review(company.id)
            return {
                "schema": _REVIEW_RESULT_SCHEMA,
                "review": asdict(existing),
                "reused": True,
                "projection": projection,
                "safety": {
                    "ai_generation_performed": False,
                    "provider_call_performed": False,
                    "business_execution_performed": False,
                    "automatic": False,
                },
            }

        matches = [
            row for row in current_recommendations(self.ai_sessions.list(company.id, limit=100))
            if row.get("recommendation_id") == recommendation_id
        ]
        if len(matches) != 1:
            raise RecommendationReviewConflict(
                "AI recommendation is no longer current. Reopen Astra / IA and review the latest session."
            )
        source = matches[0]
        row = self.ai_recommendation_reviews.record(
            company.id,
            recommendation=recommendation_id,
            session_id=str(source["session_id"]),
            digest=str(source["recommendation_sha256"]),
            decision=decision,
        )
        self.workspace.registries.timeline.append("ai.recommendation.reviewed", {
            "company_id": company.id,
            "recommendation_id": row.recommendation_id,
            "session_id": row.session_id,
            "decision": row.decision,
            "provider_call_performed": False,
            "business_execution_performed": False,
            "automatic": False,
            "recommendation_content_logged": False,
        })
        return {
            "schema": _REVIEW_RESULT_SCHEMA,
            "review": asdict(row),
            "reused": False,
            "projection": self.ai_recommendation_review(company.id),
            "safety": {
                "ai_generation_performed": False,
                "provider_call_performed": False,
                "business_execution_performed": False,
                "automatic": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Add local GET/POST review controls; no provider transport and no recommendation execution."""

    def _static(self, path: str) -> None:
        if path == "/inbox-crm-identity.js":
            target = self.server.runtime.repo_root / "web" / "inbox-crm-identity.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99AIRecommendationReview(){
  if(document.querySelector('script[data-post-w99-ai-recommendation-review]'))return;
  const script=document.createElement('script');
  script.src='/ai-recommendation-review.js';
  script.defer=true;
  script.dataset.postW99AiRecommendationReview='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/ai-recommendation-review.js":
            target = self.server.runtime.repo_root / "web" / "ai-recommendation-review.js"
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
        if path == "/ai-recommendation-review.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "recommendation-review"]:
                self._json(self.server.runtime.ai_recommendation_review(parts[2]))
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
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "recommendation-review"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.review_ai_recommendation(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
        except Exception as exc:
            if isinstance(exc, RecommendationReviewConflict):
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
    print(f"BINARIO Marketing App · post-W99 AI Recommendation Review: http://{actual_host}:{actual_port}/")
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
