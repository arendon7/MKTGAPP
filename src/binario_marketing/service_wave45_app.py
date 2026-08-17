from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .crm_store_wave45 import CRMStoreWave45
from . import service_wave44_app as base


class AppRuntime(base.AppRuntime):
    """Wave 45 adds explicit local follow-up rescheduling; all remote behavior remains unchanged."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.crm = CRMStoreWave45(runtime.data_root / "State" / "crm")
        return runtime

    def reschedule_activity(self, company_id: str, activity_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("reschedule payload must be an object")
        unknown = set(payload) - {"due_at"}
        if unknown:
            raise ValueError(f"unsupported reschedule fields: {', '.join(sorted(unknown))}")
        company = self.companies.get(company_id)
        before = self.crm.get_activity(activity_id)
        if before.company_id != company.id:
            raise KeyError(activity_id)
        row = self.crm.reschedule_activity(company.id, activity_id, payload.get("due_at"))
        self.workspace.registries.timeline.append("crm.activity.rescheduled", {
            "company_id": company.id,
            "activity_id": row.id,
            "due_from": before.due_at,
            "due_to": row.due_at,
        })
        return asdict(row)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        if urlparse(self.path).path == "/followup-reschedule.js":
            self._static("/followup-reschedule.js")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "activities" and parts[5] == "reschedule":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.reschedule_activity(parts[2], parts[4], self._body()))
                return
        except Exception as exc:
            self._wave32_error(exc)
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
