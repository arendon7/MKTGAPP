from __future__ import annotations

from dataclasses import dataclass

from .meta_graph import MetaGraphClient, MetaGraphError


@dataclass(frozen=True)
class InboxReadResult:
    conversations: tuple[dict, ...]
    comments: tuple[dict, ...]
    warnings: tuple[str, ...]


class MetaInboxReader:
    """Read-only Messenger/Instagram engagement reader using the existing Page credential."""

    def __init__(self, client: MetaGraphClient):
        self.client = client

    @classmethod
    def from_env(cls) -> "MetaInboxReader":
        return cls(MetaGraphClient.from_env())

    @staticmethod
    def _rows(payload: dict, field: str = "data") -> list[dict]:
        rows = payload.get(field, [])
        if not isinstance(rows, list):
            raise MetaGraphError("Meta returned an invalid inbox list")
        return [row for row in rows if isinstance(row, dict)]

    @staticmethod
    def _person(value) -> dict | None:
        if not isinstance(value, dict):
            return None
        person_id = str(value.get("id") or "").strip()
        username = str(value.get("username") or value.get("name") or "").strip()
        if not person_id and not username:
            return None
        return {"id": person_id or None, "username": username or None}

    def conversations(self, page_id: str, *, limit: int = 10, messages_per_conversation: int = 5) -> list[dict]:
        if limit < 1 or limit > 20:
            raise ValueError("conversation limit must be between 1 and 20")
        if messages_per_conversation < 1 or messages_per_conversation > 10:
            raise ValueError("messages per conversation must be between 1 and 10")
        page = str(page_id or "").strip()
        if not page:
            raise ValueError("Facebook Page id is required for inbox conversations")
        token = self.client._page_token(page)
        payload = self.client._request(
            "GET",
            f"{page}/conversations",
            {"limit": limit, "fields": "id,link,updated_time"},
            token=token,
        )
        result: list[dict] = []
        for conversation in self._rows(payload)[:limit]:
            conversation_id = str(conversation.get("id") or "").strip()
            if not conversation_id:
                continue
            message_list = self.client._request(
                "GET",
                conversation_id,
                {"fields": f"messages.limit({messages_per_conversation})"},
                token=token,
            )
            messages_node = message_list.get("messages")
            messages = self._rows(messages_node) if isinstance(messages_node, dict) else []
            detailed: list[dict] = []
            for message in messages[:messages_per_conversation]:
                message_id = str(message.get("id") or "").strip()
                if not message_id:
                    continue
                try:
                    detail = self.client._request(
                        "GET",
                        message_id,
                        {"fields": "id,created_time,from,to,message,reply_to"},
                        token=token,
                    )
                except MetaGraphError as exc:
                    detailed.append({
                        "id": message_id,
                        "created_time": message.get("created_time"),
                        "from": None,
                        "to": [],
                        "message": None,
                        "unavailable": True,
                        "error": str(exc)[:300],
                    })
                    continue
                to_node = detail.get("to")
                to_rows = self._rows(to_node) if isinstance(to_node, dict) else []
                detailed.append({
                    "id": message_id,
                    "created_time": detail.get("created_time") or message.get("created_time"),
                    "from": self._person(detail.get("from")),
                    "to": [person for item in to_rows if (person := self._person(item))],
                    "message": str(detail.get("message") or "")[:5000] or None,
                    "unavailable": False,
                    "error": None,
                })
            detailed.sort(key=lambda row: str(row.get("created_time") or ""), reverse=True)
            result.append({
                "id": conversation_id,
                "updated_time": conversation.get("updated_time"),
                "link": str(conversation.get("link") or "")[:1000] or None,
                "messages": detailed,
            })
        result.sort(key=lambda row: str(row.get("updated_time") or ""), reverse=True)
        return result

    def instagram_comments(self, instagram_id: str, media_ids: list[str], *, comments_per_media: int = 20) -> list[dict]:
        if comments_per_media < 1 or comments_per_media > 50:
            raise ValueError("comments per media must be between 1 and 50")
        account = str(instagram_id or "").strip()
        if not account:
            raise ValueError("Instagram professional account id is required")
        token = self.client._instagram_token(account)
        result: list[dict] = []
        seen: set[str] = set()
        for raw_media_id in media_ids[:12]:
            media_id = str(raw_media_id or "").strip()
            if not media_id or media_id in seen:
                continue
            seen.add(media_id)
            payload = self.client._request(
                "GET",
                f"{media_id}/comments",
                {"fields": "id,from,text,timestamp", "limit": comments_per_media},
                token=token,
            )
            for row in self._rows(payload)[:comments_per_media]:
                comment_id = str(row.get("id") or "").strip()
                if not comment_id:
                    continue
                result.append({
                    "id": comment_id,
                    "media_id": media_id,
                    "from": self._person(row.get("from")),
                    "text": str(row.get("text") or "")[:5000],
                    "timestamp": row.get("timestamp"),
                })
        result.sort(key=lambda row: str(row.get("timestamp") or ""), reverse=True)
        return result

    def read_company(
        self,
        *,
        page_id: str | None,
        instagram_id: str | None,
        instagram_media_ids: list[str],
        conversation_limit: int = 10,
        messages_per_conversation: int = 5,
        comments_per_media: int = 20,
    ) -> InboxReadResult:
        conversations: list[dict] = []
        comments: list[dict] = []
        warnings: list[str] = []
        if page_id:
            try:
                conversations = self.conversations(
                    page_id,
                    limit=conversation_limit,
                    messages_per_conversation=messages_per_conversation,
                )
            except MetaGraphError as exc:
                warnings.append(f"Conversations unavailable: {str(exc)[:500]}")
        else:
            warnings.append("Facebook Page not configured for this company")
        if instagram_id and instagram_media_ids:
            try:
                comments = self.instagram_comments(
                    instagram_id,
                    instagram_media_ids,
                    comments_per_media=comments_per_media,
                )
            except MetaGraphError as exc:
                warnings.append(f"Instagram comments unavailable: {str(exc)[:500]}")
        elif not instagram_id:
            warnings.append("Instagram professional account not configured for this company")
        else:
            warnings.append("No published Instagram media with remote ids is available for comment sync")
        return InboxReadResult(tuple(conversations), tuple(comments), tuple(warnings))
