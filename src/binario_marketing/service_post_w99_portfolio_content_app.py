from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_portfolio_crm_app as base
from .portfolio_content import build_portfolio_content


class AppRuntime(base.AppRuntime):
    """Add a local-only multi-company content projection on top of the post-W99 chain."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def portfolio_content(self) -> dict:
        companies = list(self.companies.list())
        contexts: dict[str, dict] = {}
        for company in companies:
            try:
                contexts[company.id] = self.creative_context(company.id)
            except Exception:
                contexts[company.id] = {"_local_state_error": True, "items": [], "counts": {}, "meta": {}}
        return build_portfolio_content(companies, contexts)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose Portfolio Content as GET-only and append its browser surface to the dev chain."""

    def _static(self, path: str) -> None:
        if path == "/portfolio-crm.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-crm.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PortfolioContent(){
  if(document.querySelector('script[data-post-w99-portfolio-content]'))return;
  const script=document.createElement('script');
  script.src='/portfolio-content.js';
  script.defer=true;
  script.dataset.postW99PortfolioContent='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/portfolio-content.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-content.js"
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
        if parsed.path == "/portfolio-content.js":
            self._static(parsed.path)
            return
        try:
            if parsed.path == "/api/portfolio/content":
                self._json(self.server.runtime.portfolio_content())
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
    print(f"BINARIO Marketing App · post-W99 Portfolio Content: http://{actual_host}:{actual_port}/")
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
