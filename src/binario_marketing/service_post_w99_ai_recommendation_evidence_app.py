from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_ai_recommendation_handoff_app as base
from .ai_recommendation_evidence import extend_action_center, project_recommendation_evidence


class AppRuntime(base.AppRuntime):
    """Observe evidence after a human-marked AI handoff without claiming causality."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def ai_recommendation_evidence(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return project_recommendation_evidence(
            company.id,
            sessions=self.ai_sessions.list(company.id, limit=100),
            resolutions=self.ai_recommendation_handoffs_store.list(company.id),
            snapshots=self.learning.list_snapshots(company.id, limit=100),
        )

    def learning_payload(self, company_id: str) -> dict:
        result = super().learning_payload(company_id)
        evidence = self.ai_recommendation_evidence(company_id)
        result["ai_recommendation_followup"] = {
            "schema": evidence["schema"],
            "summary": evidence["summary"],
            "recommendations": evidence["recommendations"],
            "contracts": evidence["contracts"],
        }
        result.setdefault("attribution", {})["ai_recommendation_causal_attribution"] = False
        result.setdefault("safety", {})["ai_recommendation_followup_read_only"] = True
        return result

    def action_center(self, company_id: str) -> dict:
        return extend_action_center(
            super().action_center(company_id),
            self.ai_recommendation_evidence(company_id),
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose post-application AI evidence as GET-only and chain its browser surface."""

    def _static(self, path: str) -> None:
        if path == "/ai-recommendation-handoff.js":
            target = self.server.runtime.repo_root / "web" / "ai-recommendation-handoff.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99AIRecommendationEvidence(){
  if(document.querySelector('script[data-post-w99-ai-recommendation-evidence]'))return;
  const script=document.createElement('script');
  script.src='/ai-recommendation-evidence.js';
  script.defer=true;
  script.dataset.postW99AiRecommendationEvidence='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/ai-recommendation-evidence.js":
            target = self.server.runtime.repo_root / "web" / "ai-recommendation-evidence.js"
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
        if path == "/ai-recommendation-evidence.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["ai", "recommendation-evidence"]:
                self._json(self.server.runtime.ai_recommendation_evidence(parts[2]))
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


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    print(f"BINARIO Marketing App · post-W99 AI Recommendation Evidence: http://{actual_host}:{actual_port}/")
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
