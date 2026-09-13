from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import service_post_w99_pilot_launch_gate_app as base
from .pilot_daily_receipt import PilotDailyReceiptStore


OPERATOR_HEADER = "X-Mercadeo-Operator"
OPERATOR_VALUE = "pilot-daily-receipt"


class AppRuntime(base.AppRuntime):
    """Cumulative post-W99 runtime with an explicit local pilot daily ledger."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.pilot_daily_receipts = PilotDailyReceiptStore(
            runtime.data_root / "State" / "pilot" / "daily_receipts.json"
        )
        return runtime


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose explicit local daily receipt writes plus minimized history reads."""

    def _static(self, path: str) -> None:
        if path == "/pilot-daily-receipt.js":
            target = self.server.runtime.repo_root / "web" / "pilot-daily-receipt.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/pilot-launch-gate.js":
            target = self.server.runtime.repo_root / "web" / "pilot-launch-gate.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            loader = b"\n;(()=>{if(document.querySelector('script[data-post-w99-pilot-daily-receipt]'))return;const s=document.createElement('script');s.src='/pilot-daily-receipt.js';s.defer=true;s.dataset.postW99PilotDailyReceipt='1';document.head.append(s)})();\n"
            body = target.read_bytes() + loader
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def _operator_request(self) -> bool:
        return self.headers.get(OPERATOR_HEADER, "") == OPERATOR_VALUE

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/pilot-launch-gate.js", "/pilot-daily-receipt.js"}:
            self._static(path)
            return
        if path == "/api/pilot/daily-receipts":
            try:
                query = parse_qs(parsed.query)
                raw_limit = (query.get("limit") or ["90"])[0]
                result = self.server.runtime.pilot_daily_receipts.list(limit=int(raw_limit))
                self._json(result)
            except (ValueError, TypeError):
                self._error(HTTPStatus.BAD_REQUEST, "invalid pilot receipt history limit")
            except (OSError, UnicodeError):
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local pilot receipt history unavailable")
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path != "/api/pilot/daily-receipts":
            super().do_POST()
            return
        if not self._operator_request():
            self._error(HTTPStatus.FORBIDDEN, "explicit local operator action required")
            return
        try:
            with self.server.mutation_lock:
                result = self.server.runtime.pilot_daily_receipts.record(self._body())
            self._json(result, HTTPStatus.CREATED)
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except (OSError, UnicodeError):
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local pilot receipt write failed")


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"MERCADEO APP · post-W99 Pilot Daily Receipt: {url}")
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
