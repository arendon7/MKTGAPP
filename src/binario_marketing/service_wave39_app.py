from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from . import service_wave38_app as ui_base
from .meta_credentials import MetaCredentialError, MetaCredentialStore
from .meta_graph import MetaGraphError
from .meta_inbox import MetaInboxReader
from .service_wave38_app import AppRuntime as Wave38Runtime


def _handle(value: object) -> str:
    return str(value or "").strip().lstrip("@").casefold()


class AppRuntime(Wave38Runtime):
    """Wave 39 adds explicit-refresh, read-only social engagement inboxes."""

    def _crm_instagram_index(self, company_id: str) -> dict[str, dict]:
        index: dict[str, dict] = {}
        for contact in self.contacts_payload(company_id):
            username = _handle(contact.get("instagram"))
            if username and username not in index:
                index[username] = {
                    "id": contact.get("id"),
                    "name": contact.get("name"),
                    "organization": contact.get("organization"),
                }
        return index

    @staticmethod
    def _contact_match(person: dict | None, index: dict[str, dict]) -> dict | None:
        if not isinstance(person, dict):
            return None
        username = _handle(person.get("username"))
        return index.get(username) if username else None

    def social_inbox(self, company_id: str, *, conversation_limit: int = 10) -> dict:
        company = self.companies.get(company_id)
        if conversation_limit < 1 or conversation_limit > 20:
            raise ValueError("inbox conversation limit must be between 1 and 20")
        try:
            credential = MetaCredentialStore().status()
        except MetaCredentialError as exc:
            return {
                "schema": "binario.marketing.social-inbox.v1",
                "company_id": company.id,
                "company_name": company.name,
                "configured": False,
                "summary": {"conversations": 0, "comments": 0, "crm_matches": 0},
                "conversations": [],
                "comments": [],
                "warnings": [f"Meta credential unavailable: {str(exc)[:500]}"],
            }
        if not credential.configured:
            return {
                "schema": "binario.marketing.social-inbox.v1",
                "company_id": company.id,
                "company_name": company.name,
                "configured": False,
                "summary": {"conversations": 0, "comments": 0, "crm_matches": 0},
                "conversations": [],
                "comments": [],
                "warnings": ["Meta is not connected"],
            }

        instagram_media_ids = [
            row.remote_id for row in self.social.list(company.id)
            if row.channel == "instagram" and row.status == "PUBLISHED" and row.remote_id
        ]
        instagram_media_ids = list(dict.fromkeys(instagram_media_ids))[:12]
        reader = MetaInboxReader.from_env()
        result = reader.read_company(
            page_id=company.facebook_page_id,
            instagram_id=company.instagram_id,
            instagram_media_ids=instagram_media_ids,
            conversation_limit=conversation_limit,
            messages_per_conversation=5,
            comments_per_media=20,
        )
        crm_index = self._crm_instagram_index(company.id)
        matches: set[str] = set()
        conversations: list[dict] = []
        for conversation in result.conversations:
            messages: list[dict] = []
            for message in conversation.get("messages", []):
                row = dict(message)
                match = self._contact_match(row.get("from"), crm_index)
                row["crm_contact"] = match
                if match and match.get("id"):
                    matches.add(str(match["id"]))
                messages.append(row)
            conversations.append({**conversation, "messages": messages})
        comments: list[dict] = []
        for comment in result.comments:
            row = dict(comment)
            match = self._contact_match(row.get("from"), crm_index)
            row["crm_contact"] = match
            if match and match.get("id"):
                matches.add(str(match["id"]))
            comments.append(row)
        return {
            "schema": "binario.marketing.social-inbox.v1",
            "company_id": company.id,
            "company_name": company.name,
            "configured": True,
            "summary": {
                "conversations": len(conversations),
                "comments": len(comments),
                "crm_matches": len(matches),
            },
            "conversations": conversations,
            "comments": comments,
            "warnings": list(result.warnings),
            "read_only": True,
            "refresh_mode": "explicit",
        }


MarketingHTTPServer = ui_base.MarketingHTTPServer


class MarketingHandler(ui_base.MarketingHandler):
    """Wave 39 inbox is GET-only and delegates every prior operation unchanged."""

    def _wave39_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, MetaGraphError):
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        elif isinstance(exc, MetaCredentialError):
            self._error(HTTPStatus.CONFLICT, str(exc))
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/audiences.js":
            self._static("/audiences-wave39-loader.js")
            return
        if path == "/audiences-wave38.js":
            self._static("/audiences-wave38-loader.js")
            return
        if path == "/inbox.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "inbox", "meta"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = str((query.get("company_id") or [""])[0]).strip()
                if not company_id:
                    raise ValueError("company_id is required for social inbox")
                raw_limit = str((query.get("limit") or ["10"])[0]).strip()
                try:
                    limit = int(raw_limit)
                except ValueError as exc:
                    raise ValueError("inbox conversation limit must be an integer") from exc
                self._json(self.server.runtime.social_inbox(company_id, conversation_limit=limit))
                return
        except Exception as exc:
            self._wave39_error(exc)
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
