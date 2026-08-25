from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_campaign_coordinate_state_decomposition_app as base


_SCHEMA = "binario.marketing.campaign-coordinate-recovery-guidance.v1"
_READY_CREATIVE_STAGES = {"READY", "SCHEDULED", "PUBLISHED", "PAID"}
_ORGANIC_CHANNELS = {"facebook_page", "instagram"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _unique(values) -> list[str]:
    result: list[str] = []
    for raw in values:
        value = _text(raw)
        if value and value not in result:
            result.append(value)
    return result


def _publication_candidate(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "channel": row.get("channel"),
        "scheduled_for": row.get("scheduled_for"),
    }


def _paid_candidate(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "campaign_name": row.get("campaign_name"),
    }


def _media_candidate(row: dict) -> dict:
    media = row.get("media") or {}
    creative = row.get("creative") or {}
    return {
        "id": media.get("id"),
        "kind": media.get("kind"),
        "stage": row.get("effective_stage"),
        "name": creative.get("title") or media.get("original_name"),
    }


def _guidance_base(diagnostic: dict) -> dict:
    return {
        "schema": _SCHEMA,
        "campaign_id": (diagnostic.get("campaign") or {}).get("id"),
        "source_coordinate_state": diagnostic.get("state"),
        "route_scope": diagnostic.get("route_scope"),
        "state": "DIAGNOSTIC_ONLY",
        "intent": "NONE",
        "owner_view": None,
        "target_kind": None,
        "target_id": None,
        "recovery_controls": [],
        "candidates": {
            "publishing_publications": [],
            "cancelled_publications": [],
            "cancelled_paid": [],
            "source_media": [],
        },
        "explanation": "The coordinate state remains diagnostic-only; no recovery owner is inferred.",
        "contracts": {
            "w64_remains_next_action_authority": True,
            "coordinate_diagnostic_remains_source_of_state": True,
            "existing_owner_mutation_authority_preserved": True,
            "exact_navigation_requires_canonical_lineage": True,
            "cancelled_objects_are_never_resurrected": True,
            "ambiguous_owner_fails_closed": True,
            "guidance_does_not_reprioritize": True,
        },
        "safety": {
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "business_mutation_performed": False,
            "automatic_retry": False,
            "automatic_recreation": False,
            "automatic_publish": False,
            "automatic_paid_activation": False,
            "background_polling": False,
            "cloud_required": False,
        },
    }


def _coordinate_recovery_from_observed(
    diagnostic: dict,
    publications: list[dict],
    paid_rows: list[dict],
    linked_creatives: list[dict],
    publication_lineage: dict[str, list[str]],
    paid_lineage: dict[str, list[str]],
) -> dict:
    """Resolve navigation/recovery guidance from exact local IDs only.

    No mutation is selected or executed here. Cancelled distribution objects are terminal;
    recovery can only point at the exact source creative so a human may create a new route.
    """
    result = _guidance_base(diagnostic)
    state = _text(diagnostic.get("state")).upper()
    publishing = [row for row in publications if _text(row.get("status")).upper() == "PUBLISHING"]
    cancelled_publications = [row for row in publications if _text(row.get("status")).upper() == "CANCELLED"]
    cancelled_paid = [row for row in paid_rows if _text(row.get("status")).upper() == "CANCELLED"]
    result["candidates"]["publishing_publications"] = [_publication_candidate(row) for row in publishing]
    result["candidates"]["cancelled_publications"] = [_publication_candidate(row) for row in cancelled_publications]
    result["candidates"]["cancelled_paid"] = [_paid_candidate(row) for row in cancelled_paid]

    if state == "PUBLICATION_IN_FLIGHT":
        result["intent"] = "OBSERVE_PUBLICATION_IN_FLIGHT"
        if len(publishing) == 1:
            target = publishing[0]
            result.update({
                "state": "EXACT_EXISTING_OWNER",
                "owner_view": "calendar",
                "target_kind": "PUBLICATION",
                "target_id": target.get("id"),
                "explanation": (
                    "Exactly one linked publication is PUBLISHING. Navigation may focus that "
                    "publication for observation, but no retry, completion or mutation control is authorized."
                ),
            })
        elif len(publishing) > 1:
            result.update({
                "state": "AMBIGUOUS_EXISTING_OWNER",
                "explanation": (
                    "More than one linked publication is PUBLISHING. Their canonical IDs are exposed "
                    "for human inspection, but no publication is selected automatically."
                ),
            })
        else:
            result.update({
                "state": "RECOVERY_INVARIANT_GAP",
                "explanation": (
                    "The coordinate diagnostic reports PUBLICATION_IN_FLIGHT but no linked publication "
                    "is currently PUBLISHING. Guidance fails closed."
                ),
            })
        return result

    if state != "ONLY_CANCELLED_DISTRIBUTION_REMAINS":
        if state in {"COORDINATE_INVARIANT_DRIFT", "UNCLASSIFIED_COORDINATION_STATE"}:
            result["explanation"] = (
                "The coordinate diagnostic is drifted or unclassified. Recovery guidance is intentionally "
                "disabled until the underlying lifecycle state is deterministic."
            )
        return result

    result["intent"] = "CREATE_NEW_DISTRIBUTION_FROM_CANCELLED_LINEAGE"
    expected_publications = int(((diagnostic.get("observed") or {}).get("publications") or {}).get("total") or 0)
    expected_paid = int(((diagnostic.get("observed") or {}).get("paid") or {}).get("total") or 0)
    if len(cancelled_publications) != expected_publications or len(cancelled_paid) != expected_paid:
        result.update({
            "state": "RECOVERY_INVARIANT_GAP",
            "explanation": (
                "The exact linked objects no longer match the cancelled-only histogram used by the coordinate "
                "diagnostic. No recovery owner is selected."
            ),
        })
        return result

    missing_lineage: list[str] = []
    source_ids: list[str] = []
    for row in cancelled_publications:
        item_id = _text(row.get("id"))
        lineage = _unique(publication_lineage.get(item_id) or [])
        if not lineage:
            missing_lineage.append(f"publication:{item_id}")
        source_ids.extend(lineage)
    for row in cancelled_paid:
        item_id = _text(row.get("id"))
        lineage = _unique(paid_lineage.get(item_id) or [])
        if not lineage:
            missing_lineage.append(f"paid:{item_id}")
        source_ids.extend(lineage)
    source_ids = _unique(source_ids)

    creative_by_id = {
        _text((row.get("media") or {}).get("id")): row
        for row in linked_creatives
        if _text((row.get("media") or {}).get("id"))
    }
    source_rows = [creative_by_id[item_id] for item_id in source_ids if item_id in creative_by_id]
    result["candidates"]["source_media"] = [_media_candidate(row) for row in source_rows]

    if missing_lineage or len(source_rows) != len(source_ids):
        result.update({
            "state": "RECOVERY_OWNER_GAP",
            "explanation": (
                "At least one cancelled distribution object cannot be traced to a unique managed creative "
                "inside this campaign. Recovery will not guess a replacement creative."
            ),
        })
        return result
    if len(source_rows) > 1:
        result.update({
            "state": "AMBIGUOUS_RECOVERY_OWNER",
            "explanation": (
                "The cancelled distribution objects originate from more than one managed creative. "
                "No source media is selected automatically."
            ),
        })
        return result
    if not source_rows:
        result.update({
            "state": "RECOVERY_OWNER_GAP",
            "explanation": "Cancelled distribution exists, but no canonical source creative lineage is available.",
        })
        return result

    source = source_rows[0]
    source_candidate = _media_candidate(source)
    if _text(source_candidate.get("stage")).upper() not in _READY_CREATIVE_STAGES:
        result.update({
            "state": "RECOVERY_OWNER_GAP",
            "explanation": (
                "The exact source creative is no longer in a W64-ready stage. It must be reviewed by its "
                "canonical creative owner before a new distribution route is prepared."
            ),
        })
        return result

    controls: list[str] = []
    cancelled_channels = _unique(row.get("channel") for row in cancelled_publications)
    if "facebook_page" in cancelled_channels:
        controls.append("PREPARE_FACEBOOK")
    if "instagram" in cancelled_channels:
        controls.append("PREPARE_INSTAGRAM")
    if cancelled_paid:
        if _text(source_candidate.get("kind")).lower() != "image":
            result.update({
                "state": "RECOVERY_OWNER_GAP",
                "explanation": (
                    "The cancelled paid route resolves to a non-image creative, while the certified W49 "
                    "Send to Paid control only accepts managed images. No substitute media is chosen."
                ),
            })
            return result
        controls.append("SEND_TO_PAID")
    controls = _unique(controls)
    if not controls:
        result.update({
            "state": "RECOVERY_OWNER_GAP",
            "explanation": "No certified W49 distribution control corresponds to the cancelled lineage.",
        })
        return result

    result.update({
        "state": "EXACT_RECOVERY_OWNER",
        "owner_view": "content",
        "target_kind": "MEDIA",
        "target_id": source_candidate.get("id"),
        "recovery_controls": controls,
        "explanation": (
            "All cancelled distribution objects trace to one W64-ready managed creative. Navigation may focus "
            "that media, but creating a replacement route remains an explicit human action in W49."
        ),
    })
    return result


def _copy_guided_rows(payload: dict, guided: dict[str, dict]) -> None:
    if payload.get("next_action"):
        action_id = _text(payload["next_action"].get("id"))
        if action_id in guided:
            payload["next_action"] = guided[action_id]
    focus = payload.get("focus") or {}
    for lane in ("now", "next", "later"):
        focus[lane] = [guided.get(_text(row.get("id")), row) for row in focus.get(lane) or []]
    payload["focus"] = focus


def _rewrite_coordinate_navigation(row: dict, guidance: dict) -> dict:
    result = deepcopy(row)
    result["coordinate_recovery"] = deepcopy(guidance)
    state = _text(guidance.get("state")).upper()
    target_kind = _text(guidance.get("target_kind")).upper()
    target_id = _text(guidance.get("target_id"))
    if state not in {"EXACT_EXISTING_OWNER", "EXACT_RECOVERY_OWNER"} or not target_id:
        return result
    action = dict(result.get("action") or {})
    if target_kind == "PUBLICATION":
        action["view"] = "calendar"
        action["tab"] = None
        action["entity_id"] = target_id
        action["label"] = "Revisar publicación en curso"
    elif target_kind == "MEDIA":
        action["view"] = "content"
        action["tab"] = None
        action["media_id"] = target_id
        action["label"] = "Preparar nueva distribución desde creativo exacto"
    result["action"] = action
    return result


class AppRuntime(base.AppRuntime):
    """Refine COORDINATE into safe observation/recovery navigation using canonical lineage."""

    def _campaign_coordinate_observation(self, company_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        creative_rows = self.company_creatives_payload(company.id)
        media_ids = set(campaign.media_ids)
        linked_creatives = [
            row for row in creative_rows
            if (row.get("media") or {}).get("id") in media_ids
            or ((row.get("creative") or {}).get("campaign_id") == campaign.id)
        ]
        for row in linked_creatives:
            media_id = _text((row.get("media") or {}).get("id"))
            if media_id:
                media_ids.add(media_id)

        publication_ids = set(campaign.publication_ids)
        paid_ids: set[str] = set()
        publication_lineage: dict[str, list[str]] = {}
        paid_lineage: dict[str, list[str]] = {}
        for row in linked_creatives:
            media_id = _text((row.get("media") or {}).get("id"))
            creative = row.get("creative") or {}
            for publication_id in creative.get("publication_ids") or []:
                item_id = _text(publication_id)
                if not item_id:
                    continue
                publication_ids.add(item_id)
                publication_lineage.setdefault(item_id, []).append(media_id)
            for draft_id in creative.get("paid_media_ids") or []:
                item_id = _text(draft_id)
                if not item_id:
                    continue
                paid_ids.add(item_id)
                paid_lineage.setdefault(item_id, []).append(media_id)

        publications: list[dict] = []
        for publication_id in sorted(publication_ids):
            try:
                row = self.social.get(publication_id)
            except KeyError:
                continue
            if row.project_id == company.id:
                publications.append(asdict(row))

        paid_rows = self.company_paid_media(company.id)
        paid_by_id = {row.get("id"): row for row in paid_rows if row.get("id")}
        linked_paid = [
            row for row in paid_rows
            if row.get("plan") and (row.get("plan") or {}).get("campaign_id") == campaign.id
        ]
        for draft_id in sorted(paid_ids):
            row = paid_by_id.get(draft_id)
            if row is not None and all(existing.get("id") != draft_id for existing in linked_paid):
                linked_paid.append(row)
        for row in linked_paid:
            draft_id = _text(row.get("id"))
            plan_media_id = _text((row.get("plan") or {}).get("company_media_id"))
            if draft_id and plan_media_id:
                paid_lineage.setdefault(draft_id, []).append(plan_media_id)

        return {
            "publications": publications,
            "paid": linked_paid,
            "linked_creatives": linked_creatives,
            "publication_lineage": {key: _unique(values) for key, values in publication_lineage.items()},
            "paid_lineage": {key: _unique(values) for key, values in paid_lineage.items()},
        }

    def campaign_coordinate_recovery_guidance(self, company_id: str, campaign_id: str) -> dict:
        diagnostic = super().campaign_coordinate_state(company_id, campaign_id)
        observation = self._campaign_coordinate_observation(company_id, campaign_id)
        return _coordinate_recovery_from_observed(
            diagnostic,
            observation["publications"],
            observation["paid"],
            observation["linked_creatives"],
            observation["publication_lineage"],
            observation["paid_lineage"],
        )

    def action_center(self, company_id: str) -> dict:
        payload = deepcopy(super().action_center(company_id))
        guided: dict[str, dict] = {}
        cache: dict[str, dict] = {}
        for row in payload.get("queue") or []:
            action_id = _text(row.get("id"))
            kind = _text(row.get("kind")).lower()
            campaign_id = _text((row.get("action") or {}).get("campaign_id"))
            current = row
            if kind == "coordinate" and campaign_id:
                try:
                    guidance = cache.get(campaign_id)
                    if guidance is None:
                        guidance = self.campaign_coordinate_recovery_guidance(company_id, campaign_id)
                        cache[campaign_id] = guidance
                    current = _rewrite_coordinate_navigation(row, guidance)
                except (KeyError, ValueError, TypeError):
                    current = row
            if action_id:
                guided[action_id] = current
        payload["queue"] = [guided.get(_text(row.get("id")), row) for row in payload.get("queue") or []]
        _copy_guided_rows(payload, guided)
        contracts = dict(payload.get("contracts") or {})
        contracts.update({
            "campaign_coordinate_recovery_uses_canonical_lineage": True,
            "campaign_coordinate_recovery_refines_navigation_only": True,
            "campaign_coordinate_cancelled_objects_remain_terminal": True,
            "campaign_coordinate_recovery_does_not_reprioritize": True,
            "campaign_coordinate_recovery_ambiguous_owner_fails_closed": True,
        })
        payload["contracts"] = contracts
        return payload


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose GET-only recovery guidance and load its zero-transport browser adapter."""

    def _static(self, path: str) -> None:
        if path == "/campaign-creative-creation-intent-handoff.js":
            target = self.server.runtime.repo_root / "web" / "campaign-creative-creation-intent-handoff.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignCoordinateRecoveryGuidance(){
  if(document.querySelector('script[data-post-w99-campaign-coordinate-recovery-guidance]'))return;
  const script=document.createElement('script');
  script.src='/campaign-coordinate-recovery-guidance.js';
  script.defer=true;
  script.dataset.postW99CampaignCoordinateRecoveryGuidance='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/campaign-coordinate-recovery-guidance.js":
            target = self.server.runtime.repo_root / "web" / "campaign-coordinate-recovery-guidance.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def _coordinate_recovery_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/campaign-coordinate-recovery-guidance.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "campaigns"
                and parts[5] == "coordinate-recovery-guidance"
            ):
                self._json(self.server.runtime.campaign_coordinate_recovery_guidance(parts[2], parts[4]))
                return
        except Exception as exc:
            self._coordinate_recovery_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Campaign Coordinate Recovery Guidance: {url}")
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
    "_coordinate_recovery_from_observed",
    "_rewrite_coordinate_navigation",
    "create_server",
    "serve",
]
