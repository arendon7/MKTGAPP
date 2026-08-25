from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_portfolio_control_tower_app as base
from .service_post_w99_executive_cockpit_app import compose_executive_cockpit


class AppRuntime(base.AppRuntime):
    """Terminal post-W99 runtime preserving Portfolio plus per-company Executive Cockpit."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def executive_cockpit(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return compose_executive_cockpit(
            company={"id": company.id, "name": company.name},
            action_center=self.action_center(company.id),
            pipeline=self.commercial_pipeline(company.id),
            outcomes=self.commercial_outcomes(company.id),
            results=self.results_intelligence_workspace(company.id),
            review=self.decision_review(company.id),
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds Executive Cockpit after Portfolio while preserving every prior route."""

    def _static(self, path: str) -> None:
        if path == "/portfolio-control-tower.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-control-tower.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99ExecutiveCockpitAfterPortfolio(){
  if(document.querySelector('script[data-post-w99-executive-cockpit]'))return;
  const script=document.createElement('script');
  script.src='/executive-cockpit.js';
  script.defer=true;
  script.dataset.postW99ExecutiveCockpit='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/executive-cockpit.js":
            target = self.server.runtime.repo_root / "web" / "executive-cockpit.js"
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
        if parsed.path == "/executive-cockpit.js":
            self._static(parsed.path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "executive-cockpit":
                self._json(self.server.runtime.executive_cockpit(parts[2]))
                return
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
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
    print(f"BINARIO Marketing App · post-W99 Portfolio + Executive Cockpit: {url}")
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
