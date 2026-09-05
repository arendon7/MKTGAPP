from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_primary_navigation_app as base
from .social_background import (
    install_social_background,
    social_background_overview,
    uninstall_social_background,
)


class AppRuntime(base.AppRuntime):
    """Post-W99 terminal exposing explicit local background scheduling controls."""

    def background_social_overview(self) -> dict:
        return social_background_overview()

    def enable_background_social(self) -> dict:
        status = install_social_background()
        self.workspace.registries.timeline.append("social.background.enabled", {
            "installed": status.installed,
            "loaded": status.loaded,
            "stale": status.stale,
            "interval_seconds": status.interval_seconds,
        })
        return social_background_overview()

    def disable_background_social(self) -> dict:
        status = uninstall_social_background()
        self.workspace.registries.timeline.append("social.background.disabled", {
            "installed": status.installed,
            "loaded": status.loaded,
        })
        return social_background_overview()


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Add explicit background scheduling UI/API without changing publication authority."""

    def _background_error(self, exc: Exception) -> None:
        if isinstance(exc, ValueError):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        elif isinstance(exc, RuntimeError):
            self._error(HTTPStatus.CONFLICT, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/primary-navigation.js":
            target = self.server.runtime.repo_root / "web" / "primary-navigation.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99SocialBackgroundControl(){
  if(document.querySelector('script[data-post-w99-social-background-control]'))return;
  const script=document.createElement('script');
  script.src='/social-background-control.js';
  script.defer=true;
  script.dataset.postW99SocialBackgroundControl='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/social-background-control.js":
            target = self.server.runtime.repo_root / "web" / "social-background-control.js"
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
        if path == "/social-background-control.js":
            self._static(path)
            return
        if path == "/api/social/background":
            try:
                self._json(self.server.runtime.background_social_overview())
            except Exception as exc:
                self._background_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/social/background/install":
            try:
                self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.enable_background_social()
                self._json(result, HTTPStatus.CREATED)
            except Exception as exc:
                self._background_error(exc)
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/social/background":
            try:
                with self.server.mutation_lock:
                    result = self.server.runtime.disable_background_social()
                self._json(result)
            except Exception as exc:
                self._background_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Social Background Control: {url}")
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
