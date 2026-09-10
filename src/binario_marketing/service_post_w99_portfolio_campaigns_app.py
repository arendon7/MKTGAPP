from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_portfolio_content_app as base
from .portfolio_campaigns import build_portfolio_campaigns


class AppRuntime(base.AppRuntime):
    """Add a local-only campaign and paid-media portfolio projection."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def portfolio_campaigns(self) -> dict:
        companies = list(self.companies.list())
        intelligence: dict[str, dict] = {}
        paid_media: dict[str, list[dict] | dict] = {}
        for company in companies:
            try:
                intelligence[company.id] = self.results_intelligence_workspace(company.id)
            except Exception:
                intelligence[company.id] = {"_local_state_error": True, "campaigns": []}
            try:
                paid_media[company.id] = self.company_paid_media(company.id)
            except Exception:
                paid_media[company.id] = {"_local_state_error": True}
        return build_portfolio_campaigns(companies, intelligence, paid_media)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose GET-only Portfolio Campaigns and append its browser adapter."""

    def _static(self, path: str) -> None:
        if path == "/portfolio-content.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-content.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PortfolioCampaigns(){
  if(document.querySelector('script[data-post-w99-portfolio-campaigns]'))return;
  const script=document.createElement('script');
  script.src='/portfolio-campaigns.js';
  script.defer=true;
  script.dataset.postW99PortfolioCampaigns='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/portfolio-campaigns.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-campaigns.js"
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
        if path == "/portfolio-campaigns.js":
            self._static(path)
            return
        try:
            if path == "/api/portfolio/campaigns":
                self._json(self.server.runtime.portfolio_campaigns())
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
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App · post-W99 Portfolio Campaigns: {url}")
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
