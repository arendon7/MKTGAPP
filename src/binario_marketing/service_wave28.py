from __future__ import annotations

from urllib.parse import urlparse

from . import service_wave27 as base
from .background_http import BackgroundSchedulingHTTPMixin
from .runtime_wave28 import AppRuntime


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(BackgroundSchedulingHTTPMixin, base.MarketingHandler):
    """Wave 27 HTTP surface plus local background-scheduling controls."""

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/background-scheduler.js":
            self._static(path)
            return
        if self._background_get(self._segments()):
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self._background_post(self._segments()):
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        if self._background_delete(self._segments()):
            return
        super().do_DELETE()


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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
