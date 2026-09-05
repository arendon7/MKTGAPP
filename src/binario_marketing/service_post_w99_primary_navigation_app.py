from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_operator_session_evidence_integration_app as base


class AppRuntime(base.AppRuntime):
    """Terminal post-W99 runtime adding presentation-only navigation consolidation."""


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Load Primary Navigation after Operator Session Evidence Integration.

    This layer changes only product navigation presentation. It adds no business
    endpoint, provider IO, storage, authority, reprioritization, or automation.
    """

    def _static(self, path: str) -> None:
        if path == "/operator-session-evidence-integration.js":
            target = self.server.runtime.repo_root / "web" / "operator-session-evidence-integration.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PrimaryNavigation(){
  if(document.querySelector('script[data-post-w99-primary-navigation]'))return;
  const script=document.createElement('script');
  script.src='/primary-navigation.js';
  script.defer=true;
  script.dataset.postW99PrimaryNavigation='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/primary-navigation.js":
            target = self.server.runtime.repo_root / "web" / "primary-navigation.js"
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
        if path == "/primary-navigation.js":
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
    print(f"BINARIO Marketing App · post-W99 Primary Navigation: {url}")
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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
