from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_pilot_data_safety_app as base


SESSION_SCHEMA = "binario.marketing.pilot-session-status.v1"


class AppRuntime(base.AppRuntime):
    """Cumulative post-W99 runtime with a minimized local pilot session projection."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    @staticmethod
    def _local_read(store_id: str, label: str, reader) -> dict:
        try:
            rows = reader()
            return {"id": store_id, "label": label, "status": "OK", "count": len(rows)}
        except Exception:
            return {"id": store_id, "label": label, "status": "ERROR", "count": None}

    def pilot_session_status(self) -> dict:
        checks = [
            self._local_read("companies", "Empresas", self.companies.list),
            self._local_read("projects", "Proyectos", self.projects.list_projects),
            self._local_read("campaigns", "Campañas", self.campaigns.list),
            self._local_read("publications", "Publicaciones", self.social.list),
        ]
        try:
            snapshot_payload = self.pilot_data_safety.list_snapshots()
            snapshots_ok = True
        except Exception:
            snapshot_payload = {"snapshots": [], "count": 0}
            snapshots_ok = False
        snapshots = list(snapshot_payload.get("snapshots") or [])
        latest = snapshots[0] if snapshots else None
        snapshot = {
            "status": "ERROR" if not snapshots_ok else ("AVAILABLE" if latest else "NONE"),
            "count": int(snapshot_payload.get("count") or 0),
            "latest": None,
            "integrity_checked": False,
        }
        if latest:
            snapshot["latest"] = {
                "id": latest.get("id"),
                "created_at": latest.get("created_at"),
                "file_count": int(latest.get("file_count") or 0),
                "total_bytes": int(latest.get("total_bytes") or 0),
            }
        local_reads_ok = all(row["status"] == "OK" for row in checks)
        overall = "READY" if local_reads_ok and snapshots_ok else "DEGRADED"
        return {
            "schema": SESSION_SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": overall,
            "backend": {"status": "OK", "mode": "LOCAL_PILOT"},
            "local_data": {
                "status": "OK" if local_reads_ok else "ERROR",
                "ready": sum(1 for row in checks if row["status"] == "OK"),
                "total": len(checks),
                "checks": checks,
            },
            "snapshot": snapshot,
            "safety": {
                "provider_reads": False,
                "provider_mutations": False,
                "credentials_read": False,
                "paths_exposed": False,
                "hashes_exposed": False,
                "automatic_polling": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Serve the pilot session status projection and its browser adapter."""

    def _static(self, path: str) -> None:
        if path == "/pilot-session-status.js":
            target = self.server.runtime.repo_root / "web" / "pilot-session-status.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/pilot-data-safety.js":
            target = self.server.runtime.repo_root / "web" / "pilot-data-safety.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            loader = b"\n;(()=>{if(document.querySelector('script[data-post-w99-pilot-session-status]'))return;const s=document.createElement('script');s.src='/pilot-session-status.js';s.defer=true;s.dataset.postW99PilotSessionStatus='1';document.head.append(s)})();\n"
            body = target.read_bytes() + loader
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/pilot-data-safety.js", "/pilot-session-status.js"}:
            self._static(path)
            return
        if path == "/api/pilot-session/status":
            self._json(self.server.runtime.pilot_session_status())
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
    print(f"MERCADEO APP · post-W99 Pilot Session Status: {url}")
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


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "SESSION_SCHEMA", "create_server", "serve"]
