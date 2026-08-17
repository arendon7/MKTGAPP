from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave39_app as base
from .inbox_reply_store import InboxReplyConflict, InboxReplyStore
from .meta_credentials import MetaCredentialError, MetaCredentialStore
from .meta_graph import MetaGraphClient, MetaGraphError
from .meta_inbox_actions import MetaInboxWriter


class AppRuntime(base.AppRuntime):
    """Wave 41 adds explicit, verified social replies to the company inbox."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.inbox_replies = InboxReplyStore(runtime.data_root / "State" / "social" / "inbox_replies")
        return runtime

    @staticmethod
    def _message_reply_eligible(page_id: str | None, message: dict) -> tuple[bool, str | None]:
        page = str(page_id or "").strip()
        if message.get("unavailable"):
            return False, "Mensaje no disponible"
        sender = message.get("from")
        sender_id = str(sender.get("id") or "").strip() if isinstance(sender, dict) else ""
        recipients = message.get("to") if isinstance(message.get("to"), list) else []
        recipient_ids = {str(row.get("id") or "").strip() for row in recipients if isinstance(row, dict)}
        if not page or not sender_id or sender_id == page or page not in recipient_ids:
            return False, "No es un mensaje entrante de esta Página"
        try:
            created = MetaInboxWriter._meta_time(message.get("created_time"))
        except ValueError:
            return False, "No se pudo validar la ventana de respuesta"
        age = datetime.now(timezone.utc) - created
        if age.total_seconds() < -300 or age.total_seconds() > 24 * 3600:
            return False, "Fuera de la ventana conservadora de 24 h"
        return True, None

    def social_inbox(self, company_id: str, *, conversation_limit: int = 10) -> dict:
        payload = super().social_inbox(company_id, conversation_limit=conversation_limit)
        company = self.companies.get(company_id)
        if not payload.get("configured"):
            payload["manual_reply_enabled"] = False
            return payload
        for conversation in payload.get("conversations", []):
            for message in conversation.get("messages", []):
                eligible, reason = self._message_reply_eligible(company.facebook_page_id, message)
                message["reply_eligible"] = eligible
                message["reply_reason"] = reason
                message["reply_kind"] = "facebook_message" if eligible else None
        known_media = {
            row.remote_id for row in self.social.list(company.id)
            if row.channel == "instagram" and row.status == "PUBLISHED" and row.remote_id
        }
        for comment in payload.get("comments", []):
            author = comment.get("from")
            author_id = str(author.get("id") or "").strip() if isinstance(author, dict) else ""
            eligible = bool(
                company.instagram_id
                and comment.get("id")
                and comment.get("media_id") in known_media
                and author_id != company.instagram_id
            )
            comment["reply_eligible"] = eligible
            comment["reply_reason"] = None if eligible else "No se pudo verificar el comentario contra contenido Instagram conocido"
            comment["reply_kind"] = "instagram_comment" if eligible else None
        payload["read_only"] = False
        payload["manual_reply_enabled"] = True
        payload["write_mode"] = "explicit-only"
        return payload

    def reply_social_inbox(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("reply payload must be an object")
        allowed = {"kind", "interaction_id", "text"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported reply fields: {', '.join(sorted(unknown))}")
        kind = str(payload.get("kind") or "").strip()
        interaction_id = str(payload.get("interaction_id") or "").strip()
        if kind not in {"facebook_message", "instagram_comment"}:
            raise ValueError("unsupported inbox reply kind")
        if not interaction_id:
            raise ValueError("interaction_id is required")
        if len(interaction_id) > 300 or any(ch in interaction_id for ch in "/?#") or any(ch.isspace() for ch in interaction_id):
            raise ValueError("invalid interaction_id")
        try:
            credential = MetaCredentialStore().status()
        except MetaCredentialError:
            raise
        if not credential.configured:
            raise MetaCredentialError("Meta is not connected")
        client = MetaGraphClient.from_env()
        writer = MetaInboxWriter(client, self.inbox_replies)
        if kind == "facebook_message":
            if not company.facebook_page_id:
                raise ValueError("Facebook Page is not configured for this company")
            result = writer.reply_facebook_message(
                company_id=company.id,
                page_id=company.facebook_page_id,
                message_id=interaction_id,
                text=payload.get("text"),
            )
        else:
            if not company.instagram_id:
                raise ValueError("Instagram professional account is not configured for this company")
            media_ids = [
                row.remote_id for row in self.social.list(company.id)
                if row.channel == "instagram" and row.status == "PUBLISHED" and row.remote_id
            ]
            result = writer.reply_instagram_comment(
                company_id=company.id,
                instagram_id=company.instagram_id,
                media_ids=list(dict.fromkeys(media_ids))[:12],
                comment_id=interaction_id,
                text=payload.get("text"),
            )
        if not result.get("reused"):
            self.workspace.registries.timeline.append("social.inbox.reply.sent", {
                "company_id": company.id,
                "kind": result.get("kind"),
                "interaction_id": result.get("interaction_id"),
                "remote_id": result.get("remote_id"),
            })
        return {
            "schema": "binario.marketing.inbox-reply.v1",
            "company_id": company.id,
            **result,
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 41 adds one explicit provider-mutation route; all prior routes delegate unchanged."""

    def _wave41_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, InboxReplyConflict):
            self._error(HTTPStatus.CONFLICT, str(exc))
        elif isinstance(exc, MetaCredentialError):
            self._error(HTTPStatus.CONFLICT, str(exc))
        elif isinstance(exc, MetaGraphError):
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/inbox-replies.js":
            self._static("/inbox-replies.js")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["inbox", "reply"]:
                with self.server.mutation_lock:
                    self._json(self.server.runtime.reply_social_inbox(parts[2], self._body()), HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave41_error(exc)
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
