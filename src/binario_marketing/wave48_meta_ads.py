from __future__ import annotations

import base64
from pathlib import Path

from .meta_ads import LinkCreativeSpec, MetaAdsBuilder, PausedAdSetSpec
from .meta_graph import MetaGraphClient, MetaGraphError


class Wave48MetaAdsBuilder:
    """Additive helpers for managed images and scheduled PAUSED ad sets.

    There is intentionally no method that sets Campaign, Ad Set or Ad to ACTIVE.
    """

    def __init__(self, client: MetaGraphClient):
        self.client = client
        self.base = MetaAdsBuilder(client)

    @staticmethod
    def _account_node(ad_account_id: str) -> str:
        value = str(ad_account_id or "").strip()
        if value.startswith("act_"):
            value = value[4:]
        if not value.isdigit():
            raise ValueError("invalid Meta ad account id")
        return f"act_{value}"

    def upload_managed_image(self, ad_account_id: str, path: Path) -> str:
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        raw = file_path.read_bytes()
        if not raw:
            raise ValueError("managed ad image is empty")
        payload = self.client._request(
            "POST",
            f"{self._account_node(ad_account_id)}/adimages",
            {"bytes": base64.b64encode(raw).decode("ascii")},
        )
        image_hash = str(payload.get("hash") or "").strip()
        if not image_hash:
            images = payload.get("images")
            if isinstance(images, dict):
                for row in images.values():
                    if isinstance(row, dict) and row.get("hash"):
                        image_hash = str(row["hash"]).strip()
                        break
        if not image_hash:
            raise MetaGraphError("Meta did not return an image hash for the managed creative")
        return image_hash

    def create_paused_adset(
        self,
        spec: PausedAdSetSpec,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> str:
        spec.validate()
        if not start_time and not end_time:
            return self.base.create_paused_adset(spec)
        payload = self.client._request(
            "POST",
            f"{self._account_node(spec.ad_account_id)}/adsets",
            {
                "name": spec.name.strip(),
                "campaign_id": spec.campaign_id.strip(),
                "daily_budget": spec.daily_budget,
                "billing_event": spec.billing_event.strip().upper(),
                "optimization_goal": spec.optimization_goal.strip().upper(),
                "bid_strategy": spec.bid_strategy.strip().upper(),
                "targeting": spec.targeting,
                "status": "PAUSED",
                "start_time": start_time,
                "end_time": end_time,
            },
        )
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return an Ad Set id")
        return remote_id

    def create_link_creative_from_hash(self, spec: LinkCreativeSpec, image_hash: str) -> str:
        spec.validate()
        value = str(image_hash or "").strip()
        if not value:
            raise ValueError("image_hash is required")
        link_data: dict = {"link": spec.link_url.strip(), "message": spec.message.strip(), "image_hash": value}
        if spec.call_to_action:
            link_data["call_to_action"] = {
                "type": spec.call_to_action.strip().upper(),
                "value": {"link": spec.link_url.strip()},
            }
        story: dict = {"page_id": spec.page_id.strip(), "link_data": link_data}
        if spec.instagram_actor_id:
            story["instagram_actor_id"] = spec.instagram_actor_id.strip()
        payload = self.client._request(
            "POST",
            f"{self._account_node(spec.ad_account_id)}/adcreatives",
            {"name": spec.name.strip(), "object_story_spec": story},
        )
        remote_id = str(payload.get("id") or "").strip()
        if not remote_id:
            raise MetaGraphError("Meta did not return an Ad Creative id")
        return remote_id


__all__ = ["Wave48MetaAdsBuilder"]
