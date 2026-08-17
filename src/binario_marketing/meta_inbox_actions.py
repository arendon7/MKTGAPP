from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .inbox_reply_store import InboxReplyStore
from .meta_graph import MetaGraphClient, MetaGraphError


class MetaInboxWriter:
    """Explicit, verified Messenger and Instagram comment replies."""

    def __init__(self, client: MetaGraphClient, checkpoints: InboxReplyStore):
        self.client = client
        self.checkpoints = checkpoints

    @staticmethod
    def _rows(payload: object) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        rows = payload.get("data", [])
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    @staticmethod
    def _meta_time(value: object) -> datetime:
        raw = str(value or "").strip()
        if not raw:
            raise ValueError("Meta message time is unavailable; reply blocked")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise ValueError("Meta message time is invalid; reply blocked") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _within_messenger_window(cls, value: object, *, now: datetime | None = None) -> bool:
        created = cls._meta_time(value)
        current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if created > current + timedelta(minutes=5):
            return False
        return current - created <= timedelta(hours=24)

    def _facebook_incoming(self, page_id: str, message_id: str) -> tuple[str, str]:
        page = str(page_id or "").strip()
        message = str(message_id or "").strip()
        if not page or not message:
            raise ValueError("Facebook Page and message ids are required")
        token = self.client._page_token(page)
        detail = self.client._request(
            "GET",
            message,
            {"fields": "id,created_time,from,to,message"},
            token=token,
        )
        if str(detail.get("id") or "").strip() != message:
            raise MetaGraphError("Meta returned a different message than requested")
        sender = detail.get("from")
        sender_id = str(sender.get("id") or "").strip() if isinstance(sender, dict) else ""
        to_node = detail.get("to")
        recipients = self._rows(to_node)
        recipient_ids = {str(row.get("id") or "").strip() for row in recipients}
        if not sender_id or sender_id == page or page not in recipient_ids:
            raise ValueError("selected message is not an incoming message to this company Page")
        if not self._within_messenger_window(detail.get("created_time")):
            raise ValueError("selected Messenger interaction is outside the conservative 24-hour response window")
        return token, sender_id

    def reply_facebook_message(self, *, company_id: str, page_id: str, message_id: str, text: object) -> dict:
        reply = self.checkpoints.normalize_text(text)
        token, recipient_id = self._facebook_incoming(page_id, message_id)
        checkpoint, reused = self.checkpoints.begin(company_id, "facebook_message", message_id, reply)
        if reused:
            return {"kind": checkpoint.kind, "interaction_id": checkpoint.interaction_id, "remote_id": checkpoint.remote_id, "reused": True}
        try:
            payload = self.client._request(
                "POST",
                f"{str(page_id).strip()}/messages",
                {
                    "messaging_type": "RESPONSE",
                    "recipient": {"id": recipient_id},
                    "message": {"text": reply},
                },
                token=token,
            )
            remote_id = str(payload.get("message_id") or "").strip()
            if not remote_id:
                raise MetaGraphError("Meta did not confirm the Messenger reply id")
        except Exception:
            self.checkpoints.ambiguous(checkpoint.key)
            raise
        sent = self.checkpoints.sent(checkpoint.key, remote_id)
        return {"kind": sent.kind, "interaction_id": sent.interaction_id, "remote_id": sent.remote_id, "reused": False}

    def _verify_instagram_comment(self, instagram_id: str, media_ids: list[str], comment_id: str) -> str:
        account = str(instagram_id or "").strip()
        comment = str(comment_id or "").strip()
        allowed = [str(value or "").strip() for value in media_ids if str(value or "").strip()]
        if not account or not comment:
            raise ValueError("Instagram account and comment ids are required")
        if not allowed:
            raise ValueError("no company Instagram media is available to verify this comment")
        token = self.client._instagram_token(account)
        for media_id in list(dict.fromkeys(allowed))[:12]:
            payload = self.client._request(
                "GET",
                f"{media_id}/comments",
                {"fields": "id,from", "limit": 50},
                token=token,
            )
            for row in self._rows(payload):
                if str(row.get("id") or "").strip() != comment:
                    continue
                author = row.get("from")
                author_id = str(author.get("id") or "").strip() if isinstance(author, dict) else ""
                if author_id and author_id == account:
                    raise ValueError("refusing to reply to a comment authored by the company Instagram account")
                return token
        raise ValueError("selected Instagram comment does not belong to recent company media known by the app")

    def reply_instagram_comment(
        self,
        *,
        company_id: str,
        instagram_id: str,
        media_ids: list[str],
        comment_id: str,
        text: object,
    ) -> dict:
        reply = self.checkpoints.normalize_text(text)
        token = self._verify_instagram_comment(instagram_id, media_ids, comment_id)
        checkpoint, reused = self.checkpoints.begin(company_id, "instagram_comment", comment_id, reply)
        if reused:
            return {"kind": checkpoint.kind, "interaction_id": checkpoint.interaction_id, "remote_id": checkpoint.remote_id, "reused": True}
        try:
            payload = self.client._request(
                "POST",
                f"{str(comment_id).strip()}/replies",
                {"message": reply},
                token=token,
            )
            remote_id = str(payload.get("id") or "").strip()
            if not remote_id:
                raise MetaGraphError("Meta did not confirm the Instagram comment reply id")
        except Exception:
            self.checkpoints.ambiguous(checkpoint.key)
            raise
        sent = self.checkpoints.sent(checkpoint.key, remote_id)
        return {"kind": sent.kind, "interaction_id": sent.interaction_id, "remote_id": sent.remote_id, "reused": False}
