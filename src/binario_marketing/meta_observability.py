from __future__ import annotations

from dataclasses import asdict
from typing import Any

from .meta_graph import MetaGraphClient, MetaGraphError
from .paid_media_store import PaidMediaDraft
from .social_store import Publication


_INSTAGRAM_MEDIA_METRICS = (
    "reach",
    "views",
    "likes",
    "comments",
    "shares",
    "saved",
    "total_interactions",
)
_AD_INSIGHT_FIELDS = (
    "ad_id",
    "date_start",
    "date_stop",
    "impressions",
    "reach",
    "clicks",
    "spend",
    "cpc",
    "cpm",
    "ctr",
    "frequency",
    "outbound_clicks",
    "actions",
    "video_play_actions",
)
_DATE_PRESETS = {
    "today",
    "yesterday",
    "last_7d",
    "last_14d",
    "last_30d",
    "this_month",
    "last_month",
    "maximum",
}


def _insight_value(row: dict[str, Any]) -> Any:
    values = row.get("values")
    if isinstance(values, list) and values:
        tail = values[-1]
        if isinstance(tail, dict) and "value" in tail:
            return tail["value"]
    return row.get("value")


def _normalize_insights(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("data", [])
    if not isinstance(rows, list):
        raise MetaGraphError("Meta returned invalid insights data")
    result: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            result[name] = _insight_value(row)
    return result


def _remote_state(payload: dict[str, Any]) -> str:
    for key in ("configured_status", "status", "effective_status"):
        value = str(payload.get(key) or "").strip().upper()
        if value:
            return value
    return "UNKNOWN"


def _is_explicitly_active(payload: dict[str, Any]) -> bool:
    return any(str(payload.get(key) or "").strip().upper() == "ACTIVE" for key in ("configured_status", "status"))


def _is_configured_paused(payload: dict[str, Any]) -> bool | None:
    values = [str(payload.get(key) or "").strip().upper() for key in ("configured_status", "status")]
    values = [value for value in values if value]
    if not values:
        return None
    return all(value == "PAUSED" for value in values)


class MetaObservability:
    """Read-only Meta state and insight readback. Never mutates provider objects."""

    def __init__(self, client: MetaGraphClient):
        self.client = client

    @classmethod
    def from_env(cls) -> "MetaObservability":
        return cls(MetaGraphClient.from_env())

    def _instagram_media_insights(self, media_id: str, instagram_id: str) -> tuple[dict[str, Any], dict[str, str]]:
        token = self.client._instagram_token(instagram_id)
        metrics = ",".join(_INSTAGRAM_MEDIA_METRICS)
        try:
            payload = self.client._request("GET", f"{media_id}/insights", {"metric": metrics}, token=token)
            return _normalize_insights(payload), {}
        except MetaGraphError:
            # Meta can reject a mixed metric set when a metric is not valid for a
            # particular media type. Retry independently so supported metrics survive.
            values: dict[str, Any] = {}
            errors: dict[str, str] = {}
            for metric in _INSTAGRAM_MEDIA_METRICS:
                try:
                    payload = self.client._request("GET", f"{media_id}/insights", {"metric": metric}, token=token)
                    values.update(_normalize_insights(payload))
                except MetaGraphError as exc:
                    errors[metric] = str(exc)
            return values, errors

    def publication(self, row: Publication) -> dict[str, Any]:
        base = {
            "publication_id": row.id,
            "channel": row.channel,
            "kind": row.kind,
            "local_status": row.status,
            "remote_id": row.remote_id,
            "available": False,
            "remote": None,
            "insights": {},
            "metric_errors": {},
        }
        if row.status != "PUBLISHED" or not row.remote_id:
            base["reason"] = "publication has no confirmed remote Meta object yet"
            return base

        if row.channel == "facebook_page":
            token = self.client._page_token(row.target_id)
            if row.kind == "reel":
                remote = self.client._request("GET", row.remote_id, {"fields": "status"}, token=token)
                base.update({"available": True, "remote": remote, "remote_state": str((remote.get("status") or {}).get("video_status") or "UNKNOWN").upper()})
                return base
            try:
                remote = self.client._request("GET", row.remote_id, {"fields": "id,created_time,permalink_url"}, token=token)
            except MetaGraphError:
                remote = self.client._request("GET", row.remote_id, {"fields": "id"}, token=token)
            base.update({"available": True, "remote": remote, "remote_state": "PRESENT"})
            return base

        if row.channel == "instagram":
            token = self.client._instagram_token(row.target_id)
            remote = self.client._request(
                "GET",
                row.remote_id,
                {"fields": "id,media_type,media_product_type,permalink,timestamp,caption"},
                token=token,
            )
            insights, metric_errors = self._instagram_media_insights(row.remote_id, row.target_id)
            base.update({
                "available": True,
                "remote": remote,
                "remote_state": "PRESENT",
                "insights": insights,
                "metric_errors": metric_errors,
            })
            return base

        base["reason"] = "unsupported publication channel"
        return base

    def paid_media(self, row: PaidMediaDraft, *, date_preset: str = "maximum") -> dict[str, Any]:
        preset = str(date_preset or "maximum").strip().lower()
        if preset not in _DATE_PRESETS:
            raise ValueError("unsupported Meta insights date_preset")

        payload: dict[str, Any] = {
            "draft_id": row.id,
            "local_status": row.status,
            "date_preset": preset,
            "available": False,
            "objects": {},
            "insights": {},
            "safety": {
                "activation_endpoint_present": False,
                "explicit_active_detected": False,
                "configured_paused": None,
            },
        }
        remote_ids = {
            "campaign": row.campaign_id,
            "adset": row.adset_id,
            "creative": row.creative_id,
            "ad": row.ad_id,
        }
        if not any(remote_ids.values()):
            payload["reason"] = "paid-media draft has no remote Meta objects yet"
            return payload

        fields = {
            "campaign": "id,name,objective,configured_status,effective_status,status,created_time,updated_time",
            "adset": "id,name,campaign_id,configured_status,effective_status,status,daily_budget,created_time,updated_time",
            "creative": "id,name",
            "ad": "id,name,campaign_id,adset_id,configured_status,effective_status,status,created_time,updated_time",
        }
        configured_paused: list[bool] = []
        explicit_active = False
        for kind, remote_id in remote_ids.items():
            if not remote_id:
                continue
            remote = self.client._request("GET", remote_id, {"fields": fields[kind]})
            remote["observed_state"] = _remote_state(remote)
            payload["objects"][kind] = remote
            if kind in {"campaign", "adset", "ad"}:
                active = _is_explicitly_active(remote)
                explicit_active = explicit_active or active
                paused = _is_configured_paused(remote)
                if paused is not None:
                    configured_paused.append(paused)

        if row.ad_id:
            insights_payload = self.client._request(
                "GET",
                f"{row.ad_id}/insights",
                {"fields": ",".join(_AD_INSIGHT_FIELDS), "date_preset": preset},
            )
            rows = insights_payload.get("data", [])
            if not isinstance(rows, list):
                raise MetaGraphError("Meta returned invalid paid-media insights data")
            payload["insights"] = rows[0] if rows and isinstance(rows[0], dict) else {}

        payload["available"] = True
        payload["safety"] = {
            "activation_endpoint_present": False,
            "explicit_active_detected": explicit_active,
            "configured_paused": (all(configured_paused) if configured_paused else None),
        }
        payload["local"] = {
            "id": row.id,
            "status": row.status,
            "campaign_id": row.campaign_id,
            "adset_id": row.adset_id,
            "creative_id": row.creative_id,
            "ad_id": row.ad_id,
        }
        return payload


__all__ = ["MetaObservability"]
