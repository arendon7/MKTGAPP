from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_campaign_media_candidate_selection_handoff_app as base


_SCHEMA = "binario.marketing.campaign-coordinate-actionability.v1"
_ALLOWED_RECOVERY_CONTROLS = {
    "PREPARE_FACEBOOK",
    "PREPARE_INSTAGRAM",
    "SEND_TO_PAID",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_coordinate(row: dict) -> bool:
    return (
        _text(row.get("source")).upper() == "CAMPAIGN"
        and _text(row.get("kind")).lower() == "coordinate"
    )


def _focus_from_queue(queue: list[dict]) -> dict:
    return {
        "now": [
            row
            for row in queue
            if _text(row.get("urgency")).upper() in {"CRITICAL", "HIGH"}
        ][:8],
        "next": [
            row
            for row in queue
            if _text(row.get("urgency")).upper() == "MEDIUM"
        ][:8],
        "later": [
            row
            for row in queue
            if _text(row.get("urgency")).upper() == "LOW"
        ][:8],
    }


def _exact_recovery_is_actionable(row: dict) -> bool:
    """Require the complete certified #137 recovery contract before Today eligibility."""
    if not _is_coordinate(row):
        return False

    diagnostic = row.get("coordinate_state") or {}
    recovery = row.get("coordinate_recovery") or {}
    action = row.get("action") or {}

    if _text(diagnostic.get("state")).upper() != "ONLY_CANCELLED_DISTRIBUTION_REMAINS":
        return False
    if (
        _text(recovery.get("source_coordinate_state")).upper()
        != "ONLY_CANCELLED_DISTRIBUTION_REMAINS"
    ):
        return False
    if _text(recovery.get("state")).upper() != "EXACT_RECOVERY_OWNER":
        return False
    if (
        _text(recovery.get("intent")).upper()
        != "CREATE_NEW_DISTRIBUTION_FROM_CANCELLED_LINEAGE"
    ):
        return False
    if _text(recovery.get("owner_view")) != "content":
        return False
    if _text(recovery.get("target_kind")).upper() != "MEDIA":
        return False

    target_id = _text(recovery.get("target_id"))
    if not target_id:
        return False
    if _text(action.get("view")) != "content":
        return False
    if _text(action.get("media_id")) != target_id:
        return False

    source_media = ((recovery.get("candidates") or {}).get("source_media") or [])
    if len(source_media) != 1 or not isinstance(source_media[0], dict):
        return False
    if _text(source_media[0].get("id")) != target_id:
        return False

    controls = list(recovery.get("recovery_controls") or [])
    if not controls:
        return False
    normalized = [_text(value).upper() for value in controls]
    if any(not value for value in normalized):
        return False
    if len(normalized) != len(set(normalized)):
        return False
    if any(value not in _ALLOWED_RECOVERY_CONTROLS for value in normalized):
        return False
    return True


def _observation_copy(row: dict) -> dict:
    observation = deepcopy(row)
    diagnostic = observation.get("coordinate_state") or {}
    recovery = observation.get("coordinate_recovery") or {}
    diagnostic_state = _text(diagnostic.get("state")).upper() or "UNKNOWN"
    recovery_state = _text(recovery.get("state")).upper() or "UNKNOWN"

    observation["requires_human_action"] = False
    observation["blocking"] = False
    observation["read_only_recommendation"] = True
    observation["actionability"] = {
        "schema": _SCHEMA,
        "state": "NON_ACTIONABLE_COORDINATE",
        "executable": False,
        "today_eligible": False,
        "owner_navigation_allowed": True,
        "reason_code": f"W64_COORDINATE_{diagnostic_state}",
        "reason": (
            "Wave64 declaró COORDINATE con requires_action=False. "
            "La fila solo permanece accionable cuando Campaign Coordinate Recovery Guidance "
            "demuestra un EXACT_RECOVERY_OWNER completo; este estado se conserva como observación."
        ),
        "coordinate_state": diagnostic_state,
        "recovery_state": recovery_state,
    }
    return observation


def preserve_coordinate_actionability(payload: dict) -> dict:
    """Keep only provable exact COORDINATE recovery in the action queue.

    Unknown, observational, ambiguous, stale and malformed COORDINATE states fail closed
    into additive observations. Relative order of all remaining queue rows is preserved.
    """
    result = deepcopy(payload)
    inherited_queue = list(result.get("queue") or [])
    actionable: list[dict] = []
    coordinate_observations: list[dict] = []
    exact_recovery_actions = 0

    for row in inherited_queue:
        if not _is_coordinate(row):
            actionable.append(row)
            continue

        if _exact_recovery_is_actionable(row):
            exact = deepcopy(row)
            exact["requires_human_action"] = True
            exact["coordinate_actionability"] = {
                "schema": _SCHEMA,
                "state": "ACTIONABLE_EXACT_RECOVERY",
                "executable": True,
                "today_eligible": True,
                "reason_code": "W64_COORDINATE_EXACT_RECOVERY_OWNER",
                "reason": (
                    "Campaign Coordinate Recovery Guidance demostró un único MEDIA canónico "
                    "y al menos un control de recuperación certificado; la ejecución sigue "
                    "dependiendo de una acción humana en el owner existente."
                ),
            }
            actionable.append(exact)
            exact_recovery_actions += 1
        else:
            coordinate_observations.append(_observation_copy(row))

    existing_observations = list(result.get("observations") or [])
    existing_ids = {_text(row.get("id")) for row in existing_observations}
    for row in coordinate_observations:
        row_id = _text(row.get("id"))
        if row_id and row_id not in existing_ids:
            existing_observations.append(row)
            existing_ids.add(row_id)

    result["queue"] = actionable
    result["next_action"] = actionable[0] if actionable else None
    result["focus"] = _focus_from_queue(actionable)
    result["observations"] = existing_observations

    urgency_counts = {key: 0 for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    source_counts = {key: 0 for key in ("OPERATIONS", "COMMERCIAL", "CAMPAIGN", "SETUP")}
    for row in actionable:
        urgency = _text(row.get("urgency")).upper()
        source = _text(row.get("source")).upper() or "OTHER"
        if urgency in urgency_counts:
            urgency_counts[urgency] += 1
        source_counts[source] = source_counts.get(source, 0) + 1

    summary = dict(result.get("summary") or {})
    summary.update(
        {
            "queue_total": len(actionable),
            "blocking": sum(1 for row in actionable if row.get("blocking")),
            "critical": urgency_counts["CRITICAL"],
            "high": urgency_counts["HIGH"],
            "medium": urgency_counts["MEDIUM"],
            "low": urgency_counts["LOW"],
            "by_source": source_counts,
            "campaign_actions": sum(
                1
                for row in actionable
                if _text(row.get("source")).upper() == "CAMPAIGN"
            ),
            "observations_total": len(existing_observations),
            # Preserve the historical Planned-Only meaning of campaign_observations.
            "campaign_observations": summary.get("campaign_observations", 0),
            "coordinate_observations": sum(
                1
                for row in existing_observations
                if _is_coordinate(row)
                and (row.get("actionability") or {}).get("state")
                == "NON_ACTIONABLE_COORDINATE"
            ),
            "coordinate_exact_recovery_actions": exact_recovery_actions,
        }
    )
    result["summary"] = summary

    contracts = dict(result.get("contracts") or {})
    contracts.update(
        {
            "coordinate_requires_exact_recovery_for_actionability": True,
            "coordinate_nonrecoverable_states_are_observational": True,
            "coordinate_observations_excluded_from_today": True,
            "unknown_coordinate_states_fail_closed": True,
            "coordinate_action_order_preserved_after_filter": True,
            "coordinate_actionability_is_read_only": True,
        }
    )
    result["contracts"] = contracts
    return result


class AppRuntime(base.AppRuntime):
    """Preserve W64 COORDINATE requires_action=False unless exact recovery is proven."""

    def action_center(self, company_id: str) -> dict:
        return preserve_coordinate_actionability(super().action_center(company_id))


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Render non-actionable coordinate observations after the current MEDIA terminal."""

    def _static(self, path: str) -> None:
        if path == "/campaign-media-candidate-selection-handoff.js":
            target = (
                self.server.runtime.repo_root
                / "web"
                / "campaign-media-candidate-selection-handoff.js"
            )
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignCoordinateActionabilityPreservation(){
  if(document.querySelector('script[data-post-w99-campaign-coordinate-actionability]'))return;
  const script=document.createElement('script');
  script.src='/campaign-coordinate-actionability.js';
  script.defer=true;
  script.dataset.postW99CampaignCoordinateActionability='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(
                HTTPStatus.OK,
                "application/javascript; charset=utf-8",
                len(body),
            )
            self.wfile.write(body)
            return
        if path == "/campaign-coordinate-actionability.js":
            target = (
                self.server.runtime.repo_root
                / "web"
                / "campaign-coordinate-actionability.js"
            )
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(
                HTTPStatus.OK,
                "application/javascript; charset=utf-8",
                len(body),
            )
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/campaign-coordinate-actionability.js":
            self._static(path)
            return
        super().do_GET()


def create_server(
    runtime: AppRuntime,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    allow_network: bool = False,
    open_browser: bool = False,
) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(
        "BINARIO Marketing App · post-W99 Campaign Coordinate Actionability Preservation: "
        f"{url}"
    )
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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = [
    "AppRuntime",
    "MarketingHandler",
    "MarketingHTTPServer",
    "_exact_recovery_is_actionable",
    "create_server",
    "preserve_coordinate_actionability",
    "serve",
]
