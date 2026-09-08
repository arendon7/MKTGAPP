from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_portfolio_inbox_refresh_app as base
from .portfolio_inbox import build_portfolio_inbox
from .portfolio_inbox_refresh import company_has_inbox_mapping


class AppRuntime(base.AppRuntime):
    """Add one local-only multi-company Inbox projection after explicit batch refresh."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def portfolio_inbox(self) -> dict:
        companies = list(self.companies.list())
        attention: dict[str, dict] = {}
        for company in companies:
            if not company_has_inbox_mapping(company):
                continue
            try:
                attention[company.id] = self.inbox_attention(company.id)
            except Exception:
                # This projection is local/read-only. Corrupt local evidence is surfaced as
                # refresh-required state instead of triggering Meta or hiding the company.
                attention[company.id] = {
                    "snapshot_state": "LOCAL_STATE_ERROR",
                    "captured_at": None,
                    "items": [],
                    "refresh_required": True,
                    "provider_read_performed": False,
                }
        return build_portfolio_inbox(companies, attention)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose the local portfolio Inbox and load its browser adapter after #174."""

    def _static(self, path: str) -> None:
        if path == "/portfolio-inbox-refresh.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-inbox-refresh.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PortfolioInbox(){
  if(document.querySelector('script[data-post-w99-portfolio-inbox]'))return;
  const script=document.createElement('script');
  script.src='/portfolio-inbox.js';
  script.defer=true;
  script.dataset.postW99PortfolioInbox='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/portfolio-inbox.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-inbox.js"
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
        if parsed.path == "/portfolio-inbox.js":
            self._static(parsed.path)
            return
        try:
            if parsed.path == "/api/portfolio/inbox-attention":
                self._json(self.server.runtime.portfolio_inbox())
                return
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:
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
    print(f"BINARIO Marketing App · post-W99 Portfolio Inbox: http://{actual_host}:{actual_port}/")
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
