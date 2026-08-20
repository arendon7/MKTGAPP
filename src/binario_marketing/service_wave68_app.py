from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

from . import service_wave67_app as base


class AppRuntime(base.AppRuntime):
    """Wave 68 adds operator guidance only; physical evidence remains manual."""


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 68 serves a guided UAT browser layer without new data or mutation routes."""

    def _static(self, path: str) -> None:
        if path == "/physical-uat.js":
            target = self.server.runtime.repo_root / "web" / "physical-uat.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave68GuidedPhysicalUAT(){
  if(document.querySelector('script[data-guided-physical-uat-wave68]'))return;
  const guided=document.createElement('script');
  guided.src='/guided-physical-uat.js';
  guided.defer=true;
  guided.dataset.guidedPhysicalUatWave68='1';
  document.head.append(guided);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/guided-physical-uat.js":
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
    print(f"BINARIO Marketing App: {url}")
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
