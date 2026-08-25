from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_campaign_execution_candidate_selector_app as base


class AppRuntime(base.AppRuntime):
    """Terminal post-W99 runtime; creative creation intent remains browser-only guidance state."""


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Loads Campaign Creative Creation Intent Handoff after the candidate selector."""

    def _static(self, path: str) -> None:
        if path == "/campaign-execution-candidate-selector.js":
            target = self.server.runtime.repo_root / "web" / "campaign-execution-candidate-selector.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignCreativeCreationIntentHandoff(){
  if(document.querySelector('script[data-post-w99-campaign-creative-creation-intent-handoff]'))return;
  const script=document.createElement('script');
  script.src='/campaign-creative-creation-intent-handoff.js';
  script.defer=true;
  script.dataset.postW99CampaignCreativeCreationIntentHandoff='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/campaign-creative-creation-intent-handoff.js":
            target = self.server.runtime.repo_root / "web" / "campaign-creative-creation-intent-handoff.js"
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
        if path == "/campaign-creative-creation-intent-handoff.js":
            self._static(path)
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
    print(f"BINARIO Marketing App · post-W99 Campaign Creative Creation Intent Handoff: {url}")
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
