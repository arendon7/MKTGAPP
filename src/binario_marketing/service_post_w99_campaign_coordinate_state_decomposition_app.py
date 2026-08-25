from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_campaign_creative_creation_intent_handoff_app as base
from .paid_media_store import STATUSES as PAID_MEDIA_STATUSES
from .social_store import STATUSES as PUBLICATION_STATUSES


_SCHEMA = "binario.marketing.campaign-coordinate-state.v1"
_TERMINAL_CAMPAIGN_STATUSES = {"COMPLETED", "ARCHIVED"}
_ORGANIC_CHANNELS = {"facebook_page", "instagram"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _count_map(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, raw in value.items():
        name = _text(key).upper() or "UNKNOWN"
        try:
            count = int(raw or 0)
        except (TypeError, ValueError):
            count = 0
        result[name] = max(0, count)
    return result


def _scope(publication_total: int, paid_total: int) -> str:
    if publication_total > 0 and paid_total > 0:
        return "MIXED"
    if publication_total > 0:
        return "ORGANIC"
    if paid_total > 0:
        return "PAID"
    return "NONE"


def _coordinate_state_from_card(card: dict) -> dict:
    """Describe why the deterministic W64 cascade reached COORDINATE.

    This helper never chooses a new next action. It mirrors earlier W64 predicates only
    to detect contradictions and then classifies the small set of states left over.
    """
    if not isinstance(card, dict):
        raise TypeError("campaign execution card must be an object")
    next_action = card.get("next_action") or {}
    if _text(next_action.get("code")).upper() != "COORDINATE":
        raise ValueError("campaign next action is not COORDINATE")

    campaign = card.get("campaign") or {}
    creative = card.get("creative") or {}
    organic = card.get("organic") or {}
    paid = card.get("paid") or {}

    channels = [_text(value) for value in (campaign.get("channels") or []) if _text(value)]
    organic_selected = bool(set(channels) & _ORGANIC_CHANNELS)
    planned_only_channels = [
        _text(value) for value in (card.get("planned_only_channels") or []) if _text(value)
    ]

    creative_counts = _count_map(creative.get("counts"))
    publication_counts = _count_map(organic.get("counts"))
    paid_counts = _count_map(paid.get("counts"))
    creative_total = int(creative.get("total") or 0)
    creative_ready = int(creative.get("ready") or 0)
    publication_total = int(organic.get("publications") or 0)
    paid_total = int(paid.get("plans") or 0)

    violations: list[str] = []
    campaign_status = _text(campaign.get("status")).upper()
    if campaign_status in _TERMINAL_CAMPAIGN_STATUSES:
        violations.append("TERMINAL_CAMPAIGN_SHOULD_COMPLETE")
    if not channels:
        violations.append("MISSING_CHANNELS_SHOULD_DEFINE_CHANNELS")
    if publication_counts.get("FAILED", 0) > 0:
        violations.append("FAILED_PUBLICATION_SHOULD_FIX_PUBLICATION")
    if creative_total == 0:
        violations.append("NO_CREATIVES_SHOULD_CREATE_CREATIVE")
    if creative_total > 0 and creative_ready == 0:
        violations.append("NO_READY_CREATIVES_SHOULD_FINISH_CREATIVE")
    if organic_selected and publication_total == 0 and paid_total == 0:
        violations.append("EMPTY_ORGANIC_DISTRIBUTION_SHOULD_PREPARE_DISTRIBUTION")
    if publication_counts.get("QUEUED", 0) > 0:
        violations.append("QUEUED_PUBLICATION_SHOULD_CALENDAR")
    if publication_counts.get("DRAFT", 0) > 0:
        violations.append("DRAFT_PUBLICATION_SHOULD_SCHEDULE_OR_PUBLISH")
    if paid_counts.get("DRAFT", 0) > 0:
        violations.append("PAID_DRAFT_SHOULD_REVIEW_PAID")
    if planned_only_channels and not organic_selected and paid_total == 0:
        violations.append("PLANNED_ONLY_CHANNELS_SHOULD_PLANNED_ONLY")
    if publication_counts.get("PUBLISHED", 0) > 0:
        violations.append("PUBLISHED_DISTRIBUTION_SHOULD_REVIEW_RESULTS")
    if paid_counts.get("REMOTE_PAUSED", 0) > 0:
        violations.append("REMOTE_PAUSED_DISTRIBUTION_SHOULD_REVIEW_RESULTS")

    if sum(creative_counts.values()) != creative_total:
        violations.append("CREATIVE_COUNT_HISTOGRAM_MISMATCH")
    if sum(publication_counts.values()) != publication_total:
        violations.append("PUBLICATION_COUNT_HISTOGRAM_MISMATCH")
    if sum(paid_counts.values()) != paid_total:
        violations.append("PAID_COUNT_HISTOGRAM_MISMATCH")
    if creative_ready < 0 or creative_ready > creative_total:
        violations.append("READY_CREATIVE_COUNT_OUT_OF_RANGE")

    unknown_publication_statuses = sorted(
        key for key, count in publication_counts.items()
        if count > 0 and key not in PUBLICATION_STATUSES
    )
    unknown_paid_statuses = sorted(
        key for key, count in paid_counts.items()
        if count > 0 and key not in PAID_MEDIA_STATUSES
    )

    if violations:
        state = "COORDINATE_INVARIANT_DRIFT"
        explanation = (
            "W64 emitted COORDINATE even though the observed card satisfies one or more "
            "earlier predicates in its deterministic cascade. No owner handoff is authorized."
        )
    elif unknown_publication_statuses or unknown_paid_statuses:
        state = "UNCLASSIFIED_COORDINATION_STATE"
        explanation = (
            "The coordination fallback contains a lifecycle status outside the currently "
            "certified publication or paid-media ontology. No behavior is inferred."
        )
    elif publication_counts.get("PUBLISHING", 0) > 0:
        state = "PUBLICATION_IN_FLIGHT"
        explanation = (
            "At least one linked publication is in the canonical PUBLISHING transition. "
            "W64 has no separate in-flight action, so COORDINATE remains observational only."
        )
    elif (
        publication_total + paid_total > 0
        and publication_counts.get("CANCELLED", 0) == publication_total
        and paid_counts.get("CANCELLED", 0) == paid_total
    ):
        state = "ONLY_CANCELLED_DISTRIBUTION_REMAINS"
        explanation = (
            "All linked distribution objects are canonically CANCELLED. The diagnostic does "
            "not infer recreation, retry, deletion, or a replacement channel."
        )
    else:
        state = "UNCLASSIFIED_COORDINATION_STATE"
        explanation = (
            "The observed fallback is not covered by the certified in-flight or cancelled-only "
            "rules. No control or next action is inferred."
        )

    return {
        "schema": _SCHEMA,
        "campaign": {
            "id": campaign.get("id"),
            "name": campaign.get("name"),
            "status": campaign.get("status"),
            "channels": channels,
        },
        "source_next_action": deepcopy(next_action),
        "state": state,
        "explanation": explanation,
        "route_scope": _scope(publication_total, paid_total),
        "observed": {
            "organic_selected": organic_selected,
            "planned_only_channels": planned_only_channels,
            "creative": {
                "total": creative_total,
                "ready": creative_ready,
                "counts": creative_counts,
            },
            "publications": {
                "total": publication_total,
                "counts": publication_counts,
            },
            "paid": {
                "total": paid_total,
                "counts": paid_counts,
            },
        },
        "invariant_violations": violations,
        "unknown_statuses": {
            "publications": unknown_publication_statuses,
            "paid": unknown_paid_statuses,
        },
        "contracts": {
            "w64_remains_next_action_authority": True,
            "diagnostic_does_not_reprioritize": True,
            "diagnostic_does_not_rewrite_action": True,
            "diagnostic_does_not_authorize_control_handoff": True,
            "unknown_states_fail_closed": True,
        },
        "safety": {
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "business_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
            "cloud_required": False,
        },
    }


def _copy_annotated_rows(payload: dict, annotated: dict[str, dict]) -> None:
    if payload.get("next_action"):
        action_id = _text(payload["next_action"].get("id"))
        if action_id in annotated:
            payload["next_action"] = annotated[action_id]
    focus = payload.get("focus") or {}
    for lane in ("now", "next", "later"):
        focus[lane] = [annotated.get(_text(row.get("id")), row) for row in focus.get(lane) or []]
    payload["focus"] = focus


class AppRuntime(base.AppRuntime):
    """Explain W64 COORDINATE fallback states without changing execution authority."""

    def campaign_coordinate_state(self, company_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        workspace = self.campaign_execution_workspace(company.id)
        cards = [
            row for row in workspace.get("campaigns") or []
            if (row.get("campaign") or {}).get("id") == campaign.id
        ]
        if len(cards) != 1:
            raise ValueError("campaign execution context is not uniquely represented")
        return _coordinate_state_from_card(cards[0])

    def action_center(self, company_id: str) -> dict:
        payload = deepcopy(super().action_center(company_id))
        annotated: dict[str, dict] = {}
        cache: dict[str, dict] = {}
        for row in payload.get("queue") or []:
            action_id = _text(row.get("id"))
            kind = _text(row.get("kind")).lower()
            campaign_id = _text((row.get("action") or {}).get("campaign_id"))
            current = row
            if kind == "coordinate" and campaign_id:
                try:
                    diagnostic = cache.get(campaign_id)
                    if diagnostic is None:
                        diagnostic = self.campaign_coordinate_state(company_id, campaign_id)
                        cache[campaign_id] = diagnostic
                    current = deepcopy(row)
                    current["coordinate_state"] = deepcopy(diagnostic)
                except (KeyError, ValueError, TypeError):
                    current = row
            if action_id:
                annotated[action_id] = current
        payload["queue"] = [annotated.get(_text(row.get("id")), row) for row in payload.get("queue") or []]
        _copy_annotated_rows(payload, annotated)
        contracts = dict(payload.get("contracts") or {})
        contracts.update({
            "campaign_coordinate_state_is_local_diagnostic": True,
            "campaign_coordinate_state_does_not_reprioritize": True,
            "campaign_coordinate_state_does_not_rewrite_action": True,
            "campaign_coordinate_state_does_not_authorize_control_handoff": True,
        })
        payload["contracts"] = contracts
        return payload


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose one GET-only diagnostic for the W64 COORDINATE fallback."""

    def _coordinate_state_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        parts = self._segments()
        try:
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "campaigns"
                and parts[5] == "coordinate-state"
            ):
                self._json(self.server.runtime.campaign_coordinate_state(parts[2], parts[4]))
                return
        except Exception as exc:
            self._coordinate_state_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Campaign Coordinate State Decomposition: {url}")
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = [
    "AppRuntime",
    "MarketingHandler",
    "MarketingHTTPServer",
    "_coordinate_state_from_card",
    "create_server",
    "serve",
]
