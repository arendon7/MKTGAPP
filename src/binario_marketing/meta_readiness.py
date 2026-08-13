from __future__ import annotations

from dataclasses import dataclass

from .meta_graph import MetaGraphClient, MetaGraphError


IG_PUBLISH_PERMISSIONS = (
    "pages_show_list",
    "instagram_basic",
    "instagram_content_publish",
    "pages_read_engagement",
)
ADS_PERMISSIONS = ("ads_read", "ads_management")
_PAGE_CONTENT_TASKS = {
    "PROFILE_PLUS_CREATE_CONTENT",
    "CREATE_CONTENT",
    "MANAGE",
    "PROFILE_PLUS_MANAGE",
    "PROFILE_PLUS_FULL_CONTROL",
}


@dataclass(frozen=True)
class ReadinessState:
    ready: bool
    missing: tuple[str, ...]
    reasons: tuple[str, ...]


def _permission_map(payload: dict) -> dict[str, str]:
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise MetaGraphError("Meta returned an invalid permissions list")
    result: dict[str, str] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("permission") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if name:
            result[name] = status
    return result


def _missing_permissions(permissions: dict[str, str], required: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(name for name in required if permissions.get(name) != "granted")


class MetaReadinessService:
    """Diagnose Meta publishing/ads readiness without exposing tokens or storing provider state."""

    def __init__(self, client: MetaGraphClient):
        self.client = client

    def permissions(self) -> dict[str, str]:
        return _permission_map(self.client._request("GET", "me/permissions"))

    def page_assets(self) -> list[dict]:
        payload = self.client._request(
            "GET",
            "me/accounts",
            {"fields": "id,name,access_token,tasks,instagram_business_account{id,username}"},
        )
        rows = payload.get("data", [])
        if not isinstance(rows, list):
            raise MetaGraphError("Meta returned an invalid Pages list")
        result = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            tasks = tuple(sorted({str(item).strip().upper() for item in (row.get("tasks") or []) if str(item).strip()}))
            instagram = row.get("instagram_business_account")
            can_create = bool(set(tasks) & _PAGE_CONTENT_TASKS)
            has_page_token = bool(str(row.get("access_token") or "").strip())
            reasons = []
            if not has_page_token:
                reasons.append("page_access_token_unavailable")
            if not can_create:
                reasons.append("page_create_content_task_missing")
            result.append({
                "id": str(row["id"]),
                "name": str(row.get("name") or ""),
                "tasks": list(tasks),
                "has_page_token": has_page_token,
                "facebook_publish_ready": has_page_token and can_create,
                "facebook_reasons": reasons,
                "instagram": {
                    "id": str(instagram.get("id")),
                    "username": str(instagram.get("username") or ""),
                } if isinstance(instagram, dict) and instagram.get("id") else None,
            })
        return result

    def diagnose(self) -> dict:
        permissions = self.permissions()
        pages = self.page_assets()
        ad_accounts = self.client.ad_accounts()

        facebook_ready = any(row["facebook_publish_ready"] for row in pages)
        facebook_reasons = []
        if not pages:
            facebook_reasons.append("no_facebook_pages")
        elif not facebook_ready:
            facebook_reasons.append("no_page_with_create_content_task")

        ig_missing = _missing_permissions(permissions, IG_PUBLISH_PERMISSIONS)
        instagram_rows = []
        for page in pages:
            instagram = page.get("instagram")
            if not instagram:
                continue
            reasons = list(ig_missing)
            if not page["has_page_token"]:
                reasons.append("page_access_token_unavailable")
            instagram_rows.append({
                "id": instagram["id"],
                "username": instagram["username"],
                "page_id": page["id"],
                "publish_ready": not reasons,
                "missing": reasons,
            })
        instagram_ready = any(row["publish_ready"] for row in instagram_rows)
        if not instagram_rows:
            ig_reasons = list(ig_missing) + ["no_linked_instagram_professional_account"]
        elif not instagram_ready:
            ig_reasons = list(ig_missing)
        else:
            ig_reasons = []

        ads_missing = _missing_permissions(permissions, ADS_PERMISSIONS)
        usable_ad_accounts = [row for row in ad_accounts if row.get("id")]
        ads_reasons = list(ads_missing)
        if not usable_ad_accounts:
            ads_reasons.append("no_ad_accounts")
        ads_ready = not ads_reasons

        return {
            "permissions": [
                {"name": name, "status": status}
                for name, status in sorted(permissions.items())
            ],
            "facebook": {
                "ready": facebook_ready,
                "reasons": facebook_reasons,
                "pages": pages,
            },
            "instagram": {
                "ready": instagram_ready,
                "required_permissions": list(IG_PUBLISH_PERMISSIONS),
                "missing_permissions": list(ig_missing),
                "reasons": ig_reasons,
                "accounts": instagram_rows,
            },
            "ads": {
                "ready": ads_ready,
                "required_permissions": list(ADS_PERMISSIONS),
                "missing_permissions": list(ads_missing),
                "reasons": ads_reasons,
                "accounts": usable_ad_accounts,
            },
        }
