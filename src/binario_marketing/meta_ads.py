from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from .meta_graph import MetaGraphClient, MetaGraphError


_ALLOWED_BILLING_EVENTS = {"IMPRESSIONS", "LINK_CLICKS"}
_ALLOWED_BID_STRATEGIES = {
    "LOWEST_COST_WITHOUT_CAP",
    "LOWEST_COST_WITH_BID_CAP",
    "COST_CAP",
    "LOWEST_COST_WITH_MIN_ROAS",
}
_ALLOWED_CTA = {
    "LEARN_MORE",
    "SHOP_NOW",
    "SIGN_UP",
    "CONTACT_US",
    "GET_OFFER",
    "APPLY_NOW",
    "BOOK_TRAVEL",
    "SUBSCRIBE",
    "NO_BUTTON",
}


def _account_path(ad_account_id: str) -> str:
    account = str(ad_account_id or "").strip()
    if account.startswith("act_"):
        account = account[4:]
    if not account or not account.isdigit():
        raise ValueError("Meta ad account id must be numeric")
    return f"act_{account}"


def _required_id(value: str, label: str) -> str:
    clean = str(value or "").strip()
    if not clean or len(clean) > 128:
        raise ValueError(f"{label} is required")
    return clean


def _https_url(value: str, label: str) -> str:
    clean = str(value or "").strip()
    parsed = urlparse(clean)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError(f"{label} must be a public HTTPS URL")
    return clean


def _validate_targeting(targeting: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(targeting, dict) or not targeting:
        raise ValueError("targeting must be a non-empty object")
    geo = targeting.get("geo_locations")
    if not isinstance(geo, dict) or not geo:
        raise ValueError("targeting.geo_locations is required")
    age_min = targeting.get("age_min")
    age_max = targeting.get("age_max")
    if age_min is not None and (not isinstance(age_min, int) or age_min < 18 or age_min > 65):
        raise ValueError("targeting.age_min must be between 18 and 65")
    if age_max is not None and (not isinstance(age_max, int) or age_max < 18 or age_max > 65):
        raise ValueError("targeting.age_max must be between 18 and 65")
    if age_min is not None and age_max is not None and age_min > age_max:
        raise ValueError("targeting age range is invalid")
    return targeting


@dataclass(frozen=True)
class PausedAdSetSpec:
    ad_account_id: str
    campaign_id: str
    name: str
    daily_budget: int
    optimization_goal: str
    targeting: dict[str, Any]
    billing_event: str = "IMPRESSIONS"
    bid_strategy: str = "LOWEST_COST_WITHOUT_CAP"

    def validate(self) -> "PausedAdSetSpec":
        _account_path(self.ad_account_id)
        _required_id(self.campaign_id, "campaign_id")
        if not self.name.strip() or len(self.name.strip()) > 255:
            raise ValueError("ad set name is required")
        if isinstance(self.daily_budget, bool) or not isinstance(self.daily_budget, int) or self.daily_budget <= 0:
            raise ValueError("daily_budget must be a positive integer in the ad account minor currency unit")
        if self.daily_budget > 2_000_000_000:
            raise ValueError("daily_budget exceeds safe API integer bounds")
        goal = self.optimization_goal.strip().upper()
        if not goal or len(goal) > 64:
            raise ValueError("optimization_goal is required")
        if self.billing_event.strip().upper() not in _ALLOWED_BILLING_EVENTS:
            raise ValueError("unsupported billing_event")
        if self.bid_strategy.strip().upper() not in _ALLOWED_BID_STRATEGIES:
            raise ValueError("unsupported bid_strategy")
        _validate_targeting(self.targeting)
        return self


@dataclass(frozen=True)
class LinkCreativeSpec:
    ad_account_id: str
    page_id: str
    name: str
    message: str
    link_url: str
    picture_url: str
    call_to_action: str = "LEARN_MORE"
    instagram_actor_id: str | None = None

    def validate(self) -> "LinkCreativeSpec":
        _account_path(self.ad_account_id)
        _required_id(self.page_id, "page_id")
        if not self.name.strip() or len(self.name.strip()) > 255:
            raise ValueError("creative name is required")
        if not self.message.strip() or len(self.message) > 5000:
            raise ValueError("creative message is required")
        _https_url(self.link_url, "link_url")
        _https_url(self.picture_url, "picture_url")
        if self.call_to_action.strip().upper() not in _ALLOWED_CTA:
            raise ValueError("unsupported call_to_action")
        if self.instagram_actor_id is not None:
            _required_id(self.instagram_actor_id, "instagram_actor_id")
        return self


@dataclass(frozen=True)
class PausedAdSpec:
    ad_account_id: str
    adset_id: str
    creative_id: str
    name: str

    def validate(self) -> "PausedAdSpec":
        _account_path(self.ad_account_id)
        _required_id(self.adset_id, "adset_id")
        _required_id(self.creative_id, "creative_id")
        if not self.name.strip() or len(self.name.strip()) > 255:
            raise ValueError("ad name is required")
        return self


class MetaAdsBuilder:
    """Build paid-media objects fail-closed. Campaign activation is intentionally out of scope."""

    def __init__(self, client: MetaGraphClient):
        self.client = client

    def create_paused_adset(self, spec: PausedAdSetSpec) -> str:
        spec.validate()
        payload = self.client._request(
            "POST",
            f"{_account_path(spec.ad_account_id)}/adsets",
            {
                "name": spec.name.strip(),
                "campaign_id": spec.campaign_id.strip(),
                "daily_budget": spec.daily_budget,
                "optimization_goal": spec.optimization_goal.strip().upper(),
                "billing_event": spec.billing_event.strip().upper(),
                "bid_strategy": spec.bid_strategy.strip().upper(),
                "targeting": spec.targeting,
                "status": "PAUSED",
            },
        )
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return an Ad Set id")
        return remote_id

    def create_link_creative(self, spec: LinkCreativeSpec) -> str:
        spec.validate()
        story: dict[str, Any] = {
            "page_id": spec.page_id.strip(),
            "link_data": {
                "call_to_action": {"type": spec.call_to_action.strip().upper()},
                "message": spec.message.strip(),
                "picture": spec.picture_url.strip(),
                "link": spec.link_url.strip(),
            },
        }
        if spec.instagram_actor_id:
            story["instagram_actor_id"] = spec.instagram_actor_id.strip()
        payload = self.client._request(
            "POST",
            f"{_account_path(spec.ad_account_id)}/adcreatives",
            {"name": spec.name.strip(), "object_story_spec": story},
        )
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return an Ad Creative id")
        return remote_id

    def create_paused_ad(self, spec: PausedAdSpec) -> str:
        spec.validate()
        payload = self.client._request(
            "POST",
            f"{_account_path(spec.ad_account_id)}/ads",
            {
                "name": spec.name.strip(),
                "adset_id": spec.adset_id.strip(),
                "creative": {"creative_id": spec.creative_id.strip()},
                "status": "PAUSED",
            },
        )
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return an Ad id")
        return remote_id
