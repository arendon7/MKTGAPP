from __future__ import annotations

import json
import re
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import service_post_w99_pilot_month_tracker_app as base
from .pilot_incident_log import PilotIncidentLog, PilotIncidentLogCorrupt


OPERATOR_HEADER = "X-Mercadeo-Operator"
OPERATOR_VALUE = "pilot-incident-log"
_RESOLVE_RE = re.compile(r"^/api/pilot/incidents/(incident_[0-9]{8}T[0-9]{6}Z_[0-9a-f]{8})/resolve$")


class AppRuntime(base.AppRuntime):
    """Cumulative post-W99 runtime with an explicit local pilot incident ledger."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.pilot_incidents = PilotIncidentLog(runtime.data_root / "State" / "pilot" / "incidents.json")
        return runtime


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose bounded local incident reads and explicit structured incident events."""

    def _static(self, path: str) -> None:
        if path == "/pilot-incident-log.js":
            target = self.server.runtime.repo_root / "web" / "pilot-incident-log.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/pilot-month-tracker.js":
            target = self.server.runtime.repo_root / "web" / "pilot-month-tracker.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            loader = b"\n;(()=>{if(document.querySelector('script[data-post-w99-pilot-incident-log]'))return;const s=document.createElement('script');s.src='/pilot-incident-log.js';s.defer=true;s.dataset.postW99PilotIncidentLog='1';document.head.append(s)})();\n"
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
        if path in {"/pilot-month-tracker.js", "/pilot-incident-log.js"}:
            self._static(path)
            return
        if path == "/api/pilot/incidents":
            query = parse_qs(parsed.query)
            status = (query.get("status") or ["ALL"])[0]
            raw_limit = (query.get("limit") or ["100"])[0]
            try:
                result = self.server.runtime.pilot_incidents.list(status=status, limit=int(raw_limit))
                self._json(result)
            except (ValueError, TypeError):
                self._error(HTTPStatus.BAD_REQUEST, "invalid pilot incident history query")
            except PilotIncidentLogCorrupt:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local pilot incident history failed integrity validation")
            except (OSError, UnicodeError, json.JSONDecodeError):
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local pilot incident history unavailable")
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        resolve_match = _RESOLVE_RE.fullmatch(path)
        if path != "/api/pilot/incidents" and resolve_match is None:
            super().do_POST()
            return
        if not self._operator_request():
            self._error(HTTPStatus.FORBIDDEN, "explicit local operator action required")
            return
        try:
            payload = self._body()
        except (ValueError, TypeError, json.JSONDecodeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        try:
            with self.server.mutation_lock:
                if path == "/api/pilot/incidents":
                    result = self.server.runtime.pilot_incidents.open(payload)
                    status = HTTPStatus.CREATED
                else:
                    result = self.server.runtime.pilot_incidents.resolve(resolve_match.group(1), payload)
                    status = HTTPStatus.OK
            self._json(result, status)
        except KeyError:
            self._error(HTTPStatus.NOT_FOUND, "pilot incident not found")
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        except PilotIncidentLogCorrupt:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local pilot incident history failed integrity validation")
        except (OSError, UnicodeError, json.JSONDecodeError):
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "local pilot incident write failed")


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"MERCADEO APP · post-W99 Pilot Incident Log: {url}")
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
