from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_pilot_journey_smoke_app as base
from .pilot_data_safety import PilotDataSafety


class AppRuntime(base.AppRuntime):
    """Cumulative post-W99 runtime with explicit local pilot data snapshots."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.pilot_data_safety = PilotDataSafety(runtime.data_root)
        return runtime


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Add local-only snapshot/list/verify endpoints and the pilot safety UI."""

    def _static(self, path: str) -> None:
        if path == "/pilot-data-safety.js":
            target = self.server.runtime.repo_root / "web" / "pilot-data-safety.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/pilot-journey-smoke.js":
            target = self.server.runtime.repo_root / "web" / "pilot-journey-smoke.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            loader = b"\n;(()=>{if(document.querySelector('script[data-post-w99-pilot-data-safety]'))return;const s=document.createElement('script');s.src='/pilot-data-safety.js';s.defer=true;s.dataset.postW99PilotDataSafety='1';document.head.append(s)})();\n"
            body = target.read_bytes() + loader
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/pilot-journey-smoke.js", "/pilot-data-safety.js"}:
            self._static(path)
            return
        if path == "/api/pilot-data-safety/snapshots":
            self._json(self.server.runtime.pilot_data_safety.list_snapshots())
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/pilot-data-safety/snapshots":
                # Creation is an explicit local operator mutation; serialize it with other local writes.
                with self.server.mutation_lock:
                    result = self.server.runtime.pilot_data_safety.create_snapshot()
                self._json(result, HTTPStatus.CREATED)
                return
            parts = [part for part in path.split("/") if part]
            if len(parts) == 5 and parts[:3] == ["api", "pilot-data-safety", "snapshots"] and parts[4] == "verify":
                result = self.server.runtime.pilot_data_safety.verify_snapshot(parts[3])
                self._json(result)
                return
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "pilot snapshot not found")
            return
        except ValueError as exc:
            # Snapshot errors are intentionally path-free and never serialize file inventory/hashes.
            self._error(HTTPStatus.CONFLICT, str(exc))
            return
        except OSError:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local snapshot operation failed")
            return
        super().do_POST()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"MERCADEO APP · post-W99 Pilot Data Safety: {url}")
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
