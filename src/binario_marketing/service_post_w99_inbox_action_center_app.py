from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_cloud_social_bridge_app as base
from .inbox_attention import InboxAttentionStore, extend_action_center, project_attention, reply_stages


class AppRuntime(base.AppRuntime):
    """Post-W99 terminal: explicit Inbox refresh becomes local Action Center evidence."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.inbox_attention_store = InboxAttentionStore(runtime.data_root / "State" / "social" / "inbox_attention")
        return runtime

    def inbox_attention(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        snapshot = self.inbox_attention_store.get(company.id)
        activities = self.crm.list_activities(company.id)
        stages = reply_stages(self.inbox_replies.root, company.id)
        return project_attention(snapshot, activities=activities, stages=stages)

    def refresh_inbox_attention(self, company_id: str) -> dict:
        """The only provider-read path added here; always operator-triggered POST."""
        company = self.companies.get(company_id)
        payload = super().social_inbox(company.id, conversation_limit=10)
        snapshot = self.inbox_attention_store.capture(
            company.id,
            page_id=company.facebook_page_id,
            instagram_id=company.instagram_id,
            payload=payload,
        )
        self.workspace.registries.timeline.append("social.inbox.attention.refreshed", {
            "company_id": company.id,
            "configured": bool(snapshot.get("configured")),
            "attention_candidates": int((snapshot.get("summary") or {}).get("attention_candidates") or 0),
            "message_body_logged": False,
            "provider_person_id_logged": False,
            "provider_link_logged": False,
            "automatic": False,
        })
        result = dict(payload)
        result["attention_snapshot"] = {
            "schema": snapshot["schema"],
            "captured_at": snapshot["captured_at"],
            "attention_candidates": int(snapshot["summary"]["attention_candidates"]),
            "persisted_locally": True,
            "secret_free": True,
        }
        return result

    def action_center(self, company_id: str) -> dict:
        return extend_action_center(super().action_center(company_id), self.inbox_attention(company_id))


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds one explicit provider refresh and one local read-only attention endpoint."""

    @staticmethod
    def _inbox_attention_route(parts: list[str]) -> tuple[str, str] | None:
        if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "inbox":
            if parts[4] in {"attention", "refresh-attention"}:
                return parts[2], parts[4]
        return None

    def _inbox_attention_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, "company not found")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            # Provider-specific errors remain normalized by the inherited inbox contract.
            self._wave41_error(exc)

    def _static(self, path: str) -> None:
        if path == "/cloud-social-bridge.js":
            target = self.server.runtime.repo_root / "web" / "cloud-social-bridge.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99InboxActionCenter(){
  if(document.querySelector('script[data-post-w99-inbox-action-center]'))return;
  const script=document.createElement('script');
  script.src='/inbox-action-center.js';
  script.defer=true;
  script.dataset.postW99InboxActionCenter='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/inbox-action-center.js":
            target = self.server.runtime.repo_root / "web" / "inbox-action-center.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/inbox-action-center.js":
            self._static(path)
            return
        route = self._inbox_attention_route(self._segments())
        if route and route[1] == "attention":
            try:
                self._json(self.server.runtime.inbox_attention(route[0]))
            except Exception as exc:
                self._inbox_attention_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        route = self._inbox_attention_route(self._segments())
        if route and route[1] == "refresh-attention":
            try:
                with self.server.mutation_lock:
                    self._json(self.server.runtime.refresh_inbox_attention(route[0]))
            except Exception as exc:
                self._inbox_attention_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Inbox Action Center: http://{actual_host}:{actual_port}/")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{actual_host}:{actual_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
