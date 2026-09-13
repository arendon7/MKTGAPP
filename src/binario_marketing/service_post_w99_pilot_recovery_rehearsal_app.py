from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_pilot_language_polish_app as base
from .pilot_recovery_rehearsal import PilotRecoveryRehearsal


class AppRuntime(base.AppRuntime):
    """Cumulative post-W99 runtime with explicit isolated recovery rehearsal."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.pilot_recovery_rehearsal = PilotRecoveryRehearsal(
            runtime.data_root,
            runtime.pilot_data_safety,
        )
        return runtime


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Add the explicit local recovery rehearsal without restore authority."""

    def _static(self, path: str) -> None:
        if path == "/pilot-recovery-rehearsal.js":
            target = self.server.runtime.repo_root / "web" / "pilot-recovery-rehearsal.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/pilot-language-polish.js":
            target = self.server.runtime.repo_root / "web" / "pilot-language-polish.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            loader = b"\n;(()=>{if(document.querySelector('script[data-post-w99-pilot-recovery-rehearsal]'))return;const s=document.createElement('script');s.src='/pilot-recovery-rehearsal.js';s.defer=true;s.dataset.postW99PilotRecoveryRehearsal='1';document.head.append(s)})();\n"
            body = target.read_bytes() + loader
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/pilot-language-polish.js", "/pilot-recovery-rehearsal.js"}:
            self._static(path)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        parts = [part for part in path.split("/") if part]
        is_rehearsal = (
            len(parts) == 5
            and parts[:3] == ["api", "pilot-data-safety", "snapshots"]
            and parts[4] == "rehearse"
        )
        if not is_rehearsal:
            super().do_POST()
            return
        if not self._operator_request():
            self._error(HTTPStatus.FORBIDDEN, "explicit local operator action required")
            return
        try:
            with self.server.mutation_lock:
                result = self.server.runtime.pilot_recovery_rehearsal.rehearse(parts[3])
            self._json(result)
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "pilot snapshot not found")
        except ValueError as exc:
            self._error(HTTPStatus.CONFLICT, str(exc))
        except OSError:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local recovery rehearsal failed")


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"MERCADEO APP · post-W99 Pilot Recovery Rehearsal: {url}")
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
