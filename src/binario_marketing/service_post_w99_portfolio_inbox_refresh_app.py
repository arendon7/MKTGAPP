from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_ai_human_feedback_context_app as base
from .portfolio_inbox_refresh import (
    aggregate_refresh_result,
    build_refresh_plan,
    company_has_inbox_mapping,
    normalize_company_ids,
)


class AppRuntime(base.AppRuntime):
    """Add one explicit, bounded multi-company provider-read convenience operation."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def portfolio_inbox_refresh_plan(self) -> dict:
        companies = list(self.companies.list())
        attention: dict[str, dict] = {}
        for company in companies:
            if not company_has_inbox_mapping(company):
                continue
            try:
                attention[company.id] = self.inbox_attention(company.id)
            except Exception:
                # A corrupt local snapshot must not make the plan perform a provider read.
                # Explicit refresh can replace it after operator confirmation.
                attention[company.id] = {
                    "snapshot_state": "LOCAL_STATE_ERROR",
                    "captured_at": None,
                    "items": [],
                    "refresh_required": True,
                    "provider_read_performed": False,
                }
        return build_refresh_plan(companies, attention)

    def refresh_portfolio_inbox_attention(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("portfolio Inbox refresh payload must be an object")
        unknown = set(payload) - {"company_ids"}
        if unknown:
            raise ValueError(f"unsupported portfolio Inbox refresh fields: {', '.join(sorted(unknown))}")
        requested = normalize_company_ids(payload.get("company_ids"))

        active = {company.id: company for company in self.companies.list()}
        invalid = [
            company_id for company_id in requested
            if company_id not in active or not company_has_inbox_mapping(active[company_id])
        ]
        if invalid:
            raise ValueError("company_ids contains an inactive, unknown, or Inbox-unmapped company")

        company_results: list[dict] = []
        for company_id in requested:
            company = active[company_id]
            try:
                refreshed = self.refresh_inbox_attention(company_id)
                snapshot = refreshed.get("attention_snapshot") or {}
                company_results.append({
                    "company_id": company_id,
                    "company_name": company.name,
                    "status": "REFRESHED",
                    "captured_at": snapshot.get("captured_at"),
                    "attention_candidates": int(snapshot.get("attention_candidates") or 0),
                })
            except Exception:
                # Failure isolation is intentional. Never return provider text or exception details
                # in a cross-company response where they could leak remote identifiers/content.
                company_results.append({
                    "company_id": company_id,
                    "company_name": company.name,
                    "status": "FAILED",
                })

        result = aggregate_refresh_result(requested, company_results)
        self.workspace.registries.timeline.append("social.inbox.portfolio_attention.refreshed", {
            "requested": result["summary"]["requested"],
            "refreshed": result["summary"]["refreshed"],
            "failed": result["summary"]["failed"],
            "company_ids": list(requested),
            "message_body_logged": False,
            "provider_person_id_logged": False,
            "provider_link_logged": False,
            "provider_error_text_logged": False,
            "automatic": False,
            "provider_mutation_performed": False,
            "crm_mutation_performed": False,
            "reply_performed": False,
        })
        return result


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose a local plan plus one explicit batch POST; preserve all prior authority boundaries."""

    def _static(self, path: str) -> None:
        if path == "/ai-recommendation-evidence.js":
            target = self.server.runtime.repo_root / "web" / "ai-recommendation-evidence.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PortfolioInboxRefresh(){
  if(document.querySelector('script[data-post-w99-portfolio-inbox-refresh]'))return;
  const script=document.createElement('script');
  script.src='/portfolio-inbox-refresh.js';
  script.defer=true;
  script.dataset.postW99PortfolioInboxRefresh='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/portfolio-inbox-refresh.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-inbox-refresh.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/portfolio-inbox-refresh.js":
            self._static(parsed.path)
            return
        try:
            if parsed.path == "/api/portfolio/inbox-refresh-plan":
                self._json(self.server.runtime.portfolio_inbox_refresh_plan())
                return
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/portfolio/inbox-refresh":
            try:
                with self.server.mutation_lock:
                    result = self.server.runtime.refresh_portfolio_inbox_attention(self._body())
                self._json(result, HTTPStatus.CREATED)
            except (ValueError, TypeError) as exc:
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            except Exception as exc:
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
    print(f"BINARIO Marketing App · post-W99 Portfolio Inbox Refresh: http://{actual_host}:{actual_port}/")
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
