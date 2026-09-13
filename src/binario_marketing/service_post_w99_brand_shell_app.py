from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from . import service_post_w99_pilot_health_summary_app as base


_TITLE_OLD = "<title>BINARIO Marketing</title>"
_TITLE_NEW = """<title>MERCADEO APP · Centro de operaciones</title>
  <meta name="application-name" content="MERCADEO APP">
  <meta name="description" content="Centro local multiempresa para operaciones de marketing.">
  <meta name="theme-color" content="#171717">
  <link rel="icon" type="image/svg+xml" href="/mercadeo-app-icon.svg">"""
_HEADER_OLD = '<div><p class="eyebrow">SISTEMA BINARIO</p><h1>Marketing Workspace</h1></div>'
_HEADER_NEW = '<div><p class="eyebrow">MERCADEO APP</p><h1>Centro de operaciones</h1></div>'


def _brand_index(source: str) -> str:
    """Return first-paint MERCADEO APP HTML without changing application behavior."""

    if _TITLE_OLD not in source or _HEADER_OLD not in source:
        raise ValueError("brand shell source contract changed")
    branded = source.replace(_TITLE_OLD, _TITLE_NEW, 1).replace(_HEADER_OLD, _HEADER_NEW, 1)
    if "BINARIO Marketing" in branded or "SISTEMA BINARIO" in branded or "Marketing Workspace" in branded:
        raise ValueError("legacy brand remained in initial shell")
    return branded


class AppRuntime(base.AppRuntime):
    """Cumulative post-W99 runtime with first-paint MERCADEO APP identity."""


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Serve branded initial HTML and a local favicon; add no business authority."""

    def _brand_root(self) -> None:
        target = self.server.runtime.repo_root / "web" / "index.html"
        if not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        try:
            body = _brand_index(target.read_text(encoding="utf-8")).encode("utf-8")
        except (OSError, UnicodeError, ValueError):
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local brand shell unavailable")
            return
        self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
        self.wfile.write(body)

    def _brand_icon(self) -> None:
        target = self.server.runtime.repo_root / "web" / "mercadeo-app-icon.svg"
        if not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        body = target.read_bytes()
        self._headers(HTTPStatus.OK, "image/svg+xml; charset=utf-8", len(body))
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._brand_root()
            return
        if path in {"/mercadeo-app-icon.svg", "/favicon.ico"}:
            self._brand_icon()
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
    print(f"MERCADEO APP · Centro de operaciones: {url}")
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
