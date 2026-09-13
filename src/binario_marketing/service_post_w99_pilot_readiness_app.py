from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_portfolio_companies_app as base


class AppRuntime(base.AppRuntime):
    """Presentation-only pilot entry layer over the cumulative post-W99 runtime."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Serve pilot identity assets without changing canonical business authority."""

    def _pilot_index(self) -> None:
        target = self.server.runtime.repo_root / "web" / "index.html"
        if not target.is_file():
            self._error(HTTPStatus.NOT_FOUND, "not found")
            return
        text = target.read_text(encoding="utf-8")
        text = text.replace(
            "<title>BINARIO Marketing</title>",
            "<title>MERCADEO APP · Centro de operaciones</title>\n"
            "  <meta name=\"theme-color\" content=\"#171717\">\n"
            "  <link rel=\"icon\" type=\"image/svg+xml\" href=\"/favicon.svg\">",
            1,
        )
        text = text.replace(
            '<div><p class="eyebrow">SISTEMA BINARIO</p><h1>Marketing Workspace</h1></div>',
            '<div><p class="eyebrow">MERCADEO APP</p><h1>Centro de operaciones</h1></div>',
            1,
        )
        if '/pilot-readiness.js' not in text:
            text = text.replace("</body>", '  <script src="/pilot-readiness.js" defer></script>\n</body>', 1)
        body = text.encode("utf-8")
        self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
        self.wfile.write(body)

    def _static(self, path: str) -> None:
        if path == "/pilot-readiness.js":
            target = self.server.runtime.repo_root / "web" / "pilot-readiness.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/favicon.svg":
            target = self.server.runtime.repo_root / "web" / "favicon.svg"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "image/svg+xml; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._pilot_index()
            return
        if path in {"/pilot-readiness.js", "/favicon.svg"}:
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
    print(f"MERCADEO APP · post-W99 Pilot Readiness: {url}")
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
