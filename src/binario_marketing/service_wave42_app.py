from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave41_app as base
from .social_store import _parse_when


class AppRuntime(base.AppRuntime):
    """Wave 42 adds safe editorial revision without mutating provider-bound identity."""

    def replace_company_publication(self, company_id: str, publication_id: str, payload: dict) -> dict:
        company, current = self._company_publication(company_id, publication_id)
        if current.status not in {"DRAFT", "QUEUED", "FAILED"}:
            raise ValueError("only draft, queued or failed publications can be revised")
        if not isinstance(payload, dict):
            raise ValueError("publication revision payload must be an object")
        allowed = {"message", "scheduled_for"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported revision fields: {', '.join(sorted(unknown))}")
        if not payload:
            raise ValueError("publication revision is empty")
        if current.render_id:
            raise ValueError("project-render publications must be revised from Content/Video Studio")

        message = current.message
        if "message" in payload:
            message = str(payload.get("message") or "").strip()
        if current.kind in {"text", "link"} and not message:
            raise ValueError("text and link publications require a message")
        if len(message) > 20000:
            raise ValueError("publication message is too long")

        if "scheduled_for" in payload:
            raw_when = str(payload.get("scheduled_for") or "").strip()
            scheduled_for = None
            if raw_when:
                parsed = _parse_when(raw_when)
                assert parsed is not None
                if parsed < datetime.now(timezone.utc) + timedelta(seconds=60):
                    raise ValueError("reprogrammed publication must be at least 60 seconds in the future")
                scheduled_for = parsed.isoformat()
        elif current.status == "QUEUED":
            parsed = _parse_when(current.scheduled_for)
            if parsed is None or parsed < datetime.now(timezone.utc) + timedelta(seconds=60):
                raise ValueError("queued publication is too close to execution; choose a new future time")
            scheduled_for = parsed.isoformat()
        else:
            scheduled_for = None

        replacement_payload = {
            "channel": current.channel,
            "target_id": current.target_id,
            "target_name": current.target_name,
            "kind": current.kind,
            "message": message,
            "link_url": current.link_url,
            "media_url": current.media_url,
            "asset_id": current.asset_id,
            "render_id": current.render_id,
            "scheduled_for": scheduled_for,
        }
        replacement = self.create_company_publication(company.id, replacement_payload)
        try:
            cancelled = self.cancel_company_publication(company.id, current.id)
        except Exception:
            try:
                self.cancel_company_publication(company.id, replacement["id"])
            except Exception as rollback_exc:
                raise RuntimeError("publication changed during revision and replacement rollback failed") from rollback_exc
            raise ValueError("publication changed while it was being revised; no replacement was left active")

        self.workspace.registries.timeline.append("company.publication.replaced", {
            "company_id": company.id,
            "publication_id": cancelled["id"],
            "replacement_publication_id": replacement["id"],
            "previous_status": current.status,
            "replacement_status": replacement["status"],
            "scheduled_for": replacement.get("scheduled_for"),
        })
        return {
            "schema": "binario.marketing.publication-revision.v1",
            "company_id": company.id,
            "previous": cancelled,
            "replacement": replacement,
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _wave42_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/editorial-management.js":
            self._static("/editorial-management.js")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "publications" and parts[5] == "replace":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.replace_company_publication(parts[2], parts[4], self._body()), HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave42_error(exc)
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
