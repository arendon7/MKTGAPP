from __future__ import annotations

from pathlib import Path

from . import service_post_w99_pilot_readiness_app as base


class AppRuntime(base.AppRuntime):
    """Cumulative post-W99 runtime with read-only cross-module pilot guidance."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Append the guidance adapter after the existing pilot entry adapter."""

    def _static(self, path: str) -> None:
        if path == "/pilot-guidance.js":
            target = self.server.runtime.repo_root / "web" / "pilot-guidance.js"
            if not target.is_file():
                self._error(404, "not found")
                return
            body = target.read_bytes()
            self._headers(200, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/pilot-readiness.js":
            target = self.server.runtime.repo_root / "web" / "pilot-readiness.js"
            if not target.is_file():
                self._error(404, "not found")
                return
            loader = b"\n;(()=>{if(document.querySelector('script[data-post-w99-pilot-guidance]'))return;const s=document.createElement('script');s.src='/pilot-guidance.js';s.defer=true;s.dataset.postW99PilotGuidance='1';document.head.append(s)})();\n"
            body = target.read_bytes() + loader
            self._headers(200, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"MERCADEO APP · post-W99 Pilot Guidance: {url}")
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
