from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


_GRAPH_VERSION_RE = re.compile(r"^v\d+\.\d+$")


class MetaGraphError(RuntimeError):
    pass


Transport = Callable[[str, str, dict[str, str]], dict]


def _default_transport(method: str, url: str, params: dict[str, str]) -> dict:
    method = method.upper()
    encoded = urlencode(params).encode("utf-8")
    request_url = url
    data = None
    if method == "GET":
        if params:
            request_url = f"{url}?{urlencode(params)}"
    else:
        data = encoded
    request = Request(
        request_url,
        data=data,
        method=method,
        headers={"Accept": "application/json", "User-Agent": "BinarioMarketing/1.0"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            graph = payload.get("error") if isinstance(payload, dict) else None
            message = str(graph.get("message") if isinstance(graph, dict) else "Meta Graph API request failed")
            code = graph.get("code") if isinstance(graph, dict) else exc.code
            raise MetaGraphError(f"Meta Graph API error {code}: {message}") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise MetaGraphError(f"Meta Graph API HTTP {exc.code}") from None
    except URLError as exc:
        raise MetaGraphError(f"Meta Graph API unavailable: {exc.reason}") from None
    if not isinstance(payload, dict):
        raise MetaGraphError("Meta Graph API returned an invalid payload")
    if isinstance(payload.get("error"), dict):
        graph = payload["error"]
        raise MetaGraphError(f"Meta Graph API error {graph.get('code', '?')}: {graph.get('message', 'request failed')}")
    return payload


@dataclass(frozen=True)
class MetaConnection:
    configured: bool
    graph_version: str
    missing: tuple[str, ...]
    publishing_ready: bool
    ads_ready: bool


class MetaGraphClient:
    """Minimal Meta Graph/Marketing API client.

    Tokens live in process environment only. Returned connection/page payloads are sanitized so
    credentials cannot accidentally flow into project state or browser JSON.
    """

    def __init__(self, access_token: str, graph_version: str = "v25.0", transport: Transport | None = None):
        token = str(access_token or "").strip()
        if not token:
            raise ValueError("Meta access token is required")
        version = str(graph_version or "").strip()
        if not _GRAPH_VERSION_RE.fullmatch(version):
            raise ValueError("invalid Meta Graph API version")
        self._access_token = token
        self.graph_version = version
        self._transport = transport or _default_transport
        self.base_url = f"https://graph.facebook.com/{version}"

    @classmethod
    def from_env(cls, transport: Transport | None = None) -> "MetaGraphClient":
        return cls(
            os.environ.get("META_ACCESS_TOKEN", ""),
            os.environ.get("META_GRAPH_API_VERSION", "v25.0"),
            transport=transport,
        )

    @staticmethod
    def diagnose_env() -> MetaConnection:
        version = os.environ.get("META_GRAPH_API_VERSION", "v25.0").strip() or "v25.0"
        missing = tuple(name for name in ("META_ACCESS_TOKEN",) if not os.environ.get(name, "").strip())
        return MetaConnection(
            configured=not missing,
            graph_version=version,
            missing=missing,
            publishing_ready=not missing,
            ads_ready=not missing,
        )

    def _request(self, method: str, path: str, params: dict | None = None, *, token: str | None = None) -> dict:
        clean = {}
        for key, value in (params or {}).items():
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple)):
                clean[str(key)] = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
            elif isinstance(value, bool):
                clean[str(key)] = "true" if value else "false"
            else:
                clean[str(key)] = str(value)
        clean["access_token"] = token or self._access_token
        return self._transport(method.upper(), f"{self.base_url}/{path.lstrip('/')}", clean)

    def _pages_with_tokens(self) -> list[dict]:
        payload = self._request(
            "GET",
            "me/accounts",
            {"fields": "id,name,access_token,instagram_business_account{id,username}"},
        )
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise MetaGraphError("Meta returned an invalid Pages list")
        return [row for row in rows if isinstance(row, dict) and row.get("id")]

    def pages(self) -> list[dict]:
        result = []
        for row in self._pages_with_tokens():
            instagram = row.get("instagram_business_account")
            result.append({
                "id": str(row["id"]),
                "name": str(row.get("name") or ""),
                "page_token_available": bool(row.get("access_token")),
                "instagram": {
                    "id": str(instagram.get("id")),
                    "username": str(instagram.get("username") or ""),
                } if isinstance(instagram, dict) and instagram.get("id") else None,
            })
        return result

    def _page_token(self, page_id: str) -> str:
        wanted = str(page_id).strip()
        for row in self._pages_with_tokens():
            if str(row.get("id")) == wanted:
                token = str(row.get("access_token") or "").strip()
                if not token:
                    raise MetaGraphError("Meta did not return a Page access token for the selected Page")
                return token
        raise MetaGraphError("selected Facebook Page is not available to this Meta connection")

    def ad_accounts(self) -> list[dict]:
        payload = self._request(
            "GET",
            "me/adaccounts",
            {"fields": "id,name,account_id,account_status,currency,timezone_name"},
        )
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise MetaGraphError("Meta returned an invalid ad account list")
        return [
            {
                "id": str(row.get("id") or ""),
                "account_id": str(row.get("account_id") or ""),
                "name": str(row.get("name") or ""),
                "account_status": row.get("account_status"),
                "currency": row.get("currency"),
                "timezone_name": row.get("timezone_name"),
            }
            for row in rows if isinstance(row, dict) and row.get("id")
        ]

    def publish_page_feed(self, page_id: str, message: str, link_url: str | None = None) -> str:
        text = str(message or "").strip()
        if not text:
            raise ValueError("Facebook Page post message is required")
        params = {"message": text}
        if link_url:
            params["link"] = str(link_url).strip()
        payload = self._request("POST", f"{page_id}/feed", params, token=self._page_token(page_id))
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return a Facebook post id")
        return remote_id

    def publish_page_photo(self, page_id: str, image_url: str, caption: str = "") -> str:
        url = str(image_url or "").strip()
        if not url.startswith(("https://", "http://")):
            raise ValueError("Facebook image publication requires a public image URL")
        payload = self._request(
            "POST",
            f"{page_id}/photos",
            {"url": url, "caption": str(caption or "")},
            token=self._page_token(page_id),
        )
        remote_id = str(payload.get("post_id") or payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return a Facebook photo id")
        return remote_id

    def create_instagram_container(self, instagram_id: str, media_url: str, caption: str, kind: str) -> str:
        kind = str(kind).strip().lower()
        url = str(media_url or "").strip()
        if not url.startswith(("https://", "http://")):
            raise ValueError("Instagram publication requires a public media URL")
        if kind not in {"image", "reel"}:
            raise ValueError("Instagram kind must be image or reel")
        params = {"caption": str(caption or "")}
        if kind == "image":
            params["image_url"] = url
        else:
            params["media_type"] = "REELS"
            params["video_url"] = url
        payload = self._request("POST", f"{instagram_id}/media", params)
        container_id = str(payload.get("id") or "").strip()
        if not container_id:
            raise MetaGraphError("Meta did not return an Instagram container id")
        return container_id

    def instagram_container_status(self, container_id: str) -> str:
        payload = self._request("GET", str(container_id), {"fields": "status_code,status"})
        return str(payload.get("status_code") or payload.get("status") or "").strip().upper()

    def publish_instagram_container(self, instagram_id: str, container_id: str) -> str:
        payload = self._request("POST", f"{instagram_id}/media_publish", {"creation_id": container_id})
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return an Instagram media id")
        return remote_id

    def create_paused_campaign(self, ad_account_id: str, *, name: str, objective: str, special_ad_categories: list[str] | None = None) -> str:
        account = str(ad_account_id or "").strip()
        if account.startswith("act_"):
            account = account[4:]
        if not account:
            raise ValueError("Meta ad account id is required")
        campaign_name = str(name or "").strip()
        if not campaign_name:
            raise ValueError("campaign name is required")
        campaign_objective = str(objective or "").strip().upper()
        if not campaign_objective.startswith("OUTCOME_"):
            raise ValueError("campaign objective must use current OUTCOME_* naming")
        payload = self._request(
            "POST",
            f"act_{account}/campaigns",
            {
                "name": campaign_name,
                "objective": campaign_objective,
                "status": "PAUSED",
                "special_ad_categories": special_ad_categories or [],
            },
        )
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return a campaign id")
        return remote_id
