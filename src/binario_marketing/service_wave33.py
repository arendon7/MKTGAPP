from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave32 as base
from .background_scheduler import install_locked_scheduler
from .background_service import BackgroundServiceError, BackgroundServiceManager
from .social_process_lock import social_queue_lock


class AppRuntime(base.AppRuntime):
    """Wave 32 operations/CRM plus opt-in, cross-process-safe macOS scheduling."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        install_locked_scheduler(runtime)
        runtime.background_service = BackgroundServiceManager(data_root=runtime.data_root)
        return runtime

    def background_scheduling_status(self) -> dict:
        payload = self.background_service.status()
        scheduler = self.social_scheduler
        payload["desktop_scheduler"] = scheduler.status() if scheduler is not None else None
        rows = self.social.list()
        payload["queue"] = {
            "queued": sum(1 for row in rows if row.status == "QUEUED"),
            "publishing": sum(1 for row in rows if row.status == "PUBLISHING"),
            "failed": sum(1 for row in rows if row.status == "FAILED"),
        }
        return payload

    def register_background_scheduling(self) -> dict:
        return self.background_service.register()

    def unregister_background_scheduling(self) -> dict:
        return self.background_service.unregister()

    def open_background_settings(self) -> dict:
        return self.background_service.open_settings()

    def publish_publication_now(self, project_id: str, publication_id: str) -> dict:
        with social_queue_lock(self.social.root, timeout=2.0) as acquired:
            if not acquired:
                raise ValueError("publication queue is busy; retry shortly")
            return super().publish_publication_now(project_id, publication_id)

    def publish_company_publication_now(self, company_id: str, publication_id: str) -> dict:
        with social_queue_lock(self.social.root, timeout=2.0) as acquired:
            if not acquired:
                raise ValueError("publication queue is busy; retry shortly")
            return super().publish_company_publication_now(company_id, publication_id)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Background scheduling control surface; all Wave 32 and legacy routes delegate."""

    def _wave33_error(self, exc: Exception) -> None:
        if isinstance(exc, BackgroundServiceError):
            self._error(HTTPStatus.CONFLICT, str(exc))
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/background-scheduling.js":
            self._static(path)
            return
        if self._segments() == ["api", "background-scheduling"]:
            try:
                self._json(self.server.runtime.background_scheduling_status())
            except Exception as exc:
                self._wave33_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        if parts in (
            ["api", "background-scheduling", "register"],
            ["api", "background-scheduling", "open-settings"],
        ):
            try:
                with self.server.mutation_lock:
                    if parts[-1] == "register":
                        self._json(self.server.runtime.register_background_scheduling())
                    else:
                        self._json(self.server.runtime.open_background_settings())
            except Exception as exc:
                self._wave33_error(exc)
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        if self._segments() == ["api", "background-scheduling"]:
            try:
                with self.server.mutation_lock:
                    self._json(self.server.runtime.unregister_background_scheduling())
            except Exception as exc:
                self._wave33_error(exc)
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
