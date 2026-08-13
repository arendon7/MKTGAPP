from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from . import service as base
from .wave27_instagram_local import Wave27MetaSocialPublisher, install_wave27_social


class AppRuntime(base.AppRuntime):
    """Canonical service runtime plus isolated Wave 27 Instagram-local social support."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        install_wave27_social(runtime)
        return runtime

    def publish_publication_now(self, project_id: str, publication_id: str) -> dict:
        row = self._publication_for_project(project_id, publication_id)
        if row.status in {"DRAFT", "FAILED"}:
            row = self.social.queue(publication_id)
        if row.status != "QUEUED":
            raise ValueError("publication cannot be published from its current state")
        scheduler = self.social_scheduler
        if scheduler is None:
            raise RuntimeError("Wave 27 social scheduler is unavailable")
        client = scheduler.client_factory()
        result = asdict(Wave27MetaSocialPublisher(self.social, client).publish(publication_id))
        self._record_social_results([result])
        return result


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds only the Wave 27 static bundle; every API route stays canonical."""

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/instagram-local-reel.js":
            self._static("/instagram-local-reel.js")
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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
