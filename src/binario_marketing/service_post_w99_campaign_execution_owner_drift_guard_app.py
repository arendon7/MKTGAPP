from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_setup_readiness_owner_handoff_app as base


_OWNER_DRIFT_SCHEMA = "binario.marketing.campaign-execution-owner-drift.v1"
_NO_TARGET_RULES = {
    "FIX_PUBLICATION": {"owner_view": "calendar", "expected_target_kind": "PUBLICATION"},
    "SCHEDULE_OR_PUBLISH": {"owner_view": "calendar", "expected_target_kind": "PUBLICATION"},
    "REVIEW_PAID": {"owner_view": "pauta", "expected_target_kind": "PAID_DRAFT"},
    "FINISH_CREATIVE": {"owner_view": "content", "expected_target_kind": "MEDIA"},
    "PREPARE_DISTRIBUTION": {"owner_view": "content", "expected_target_kind": "MEDIA"},
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _zero_candidate_count(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return value == 0
    if isinstance(value, str):
        return value.strip() == "0"
    return False


def _owner_drift(row: dict) -> dict | None:
    resolution = row.get("owner_resolution")
    if not isinstance(resolution, dict):
        return None
    if _text(resolution.get("state")).upper() != "NO_TARGET":
        return None
    source_code = _text(resolution.get("source_code")).upper()
    rule = _NO_TARGET_RULES.get(source_code)
    if rule is None or _text(resolution.get("owner_view")) != rule["owner_view"]:
        return None
    if _text(resolution.get("target_id")) or not _zero_candidate_count(resolution.get("candidate_count")):
        return None
    candidates = resolution.get("candidates")
    if not isinstance(candidates, list) or candidates:
        return None
    action = row.get("action")
    if not isinstance(action, dict):
        return None
    campaign_id = _text(action.get("campaign_id"))
    if not campaign_id:
        return None
    return {
        "schema": _OWNER_DRIFT_SCHEMA,
        "state": "CANONICAL_TARGET_NOT_PRESENT",
        "source_code": source_code,
        "owner_view": rule["owner_view"],
        "expected_target_kind": rule["expected_target_kind"],
        "campaign_id": campaign_id,
        "target_selected": False,
        "replacement_inferred": False,
        "recovery": {
            "mode": "OPEN_OWNER_AND_REVIEW_CURRENT_STATE",
            "view": rule["owner_view"],
            "requires_human_review": True,
        },
        "reason": _text(resolution.get("reason")) or (
            "La siguiente acción de W64 ya no tiene un objeto canónico presente que pueda abrirse por ID exacto."
        ),
    }


def annotate_campaign_execution_owner_drift(payload: dict) -> dict:
    result = deepcopy(payload)
    routed: dict[str, dict] = {}
    observations: list[dict] = []
    for row in result.get("queue") or []:
        action_id = _text(row.get("id"))
        current = row
        drift = _owner_drift(row) if action_id else None
        if drift is not None:
            current = deepcopy(row)
            current["owner_drift"] = drift
            observations.append({"action_id": action_id, **deepcopy(drift)})
        if action_id:
            routed[action_id] = current
    result["queue"] = [routed.get(_text(row.get("id")), row) for row in result.get("queue") or []]
    if result.get("next_action"):
        action_id = _text(result["next_action"].get("id"))
        if action_id in routed:
            result["next_action"] = routed[action_id]
    focus = result.get("focus") or {}
    for lane in ("now", "next", "later"):
        focus[lane] = [routed.get(_text(row.get("id")), row) for row in focus.get(lane) or []]
    result["focus"] = focus
    result["owner_drift_observations"] = observations
    contracts = dict(result.get("contracts") or {})
    contracts.update({
        "no_target_is_observable": True,
        "no_target_preserves_w64_priority": True,
        "no_target_does_not_select_replacement": True,
        "no_target_owner_recovery_is_navigation_only": True,
        "malformed_no_target_fails_closed": True,
        "owner_drift_human_review_required": True,
        "owner_drift_runs_after_campaign_actionability_filters": True,
        "owner_drift_runs_after_setup_readiness_handoff": True,
    })
    result["contracts"] = contracts
    return result


class AppRuntime(base.AppRuntime):
    def action_center(self, company_id: str) -> dict:
        return annotate_campaign_execution_owner_drift(super().action_center(company_id))


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path == "/setup-readiness-owner-handoff.js":
            target = self.server.runtime.repo_root / "web" / "setup-readiness-owner-handoff.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignExecutionOwnerDriftGuard(){
  if(document.querySelector('script[data-post-w99-campaign-execution-owner-drift-guard]'))return;
  const script=document.createElement('script');
  script.src='/campaign-execution-owner-drift-guard.js';
  script.defer=true;
  script.dataset.postW99CampaignExecutionOwnerDriftGuard='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/campaign-execution-owner-drift-guard.js":
            target = self.server.runtime.repo_root / "web" / "campaign-execution-owner-drift-guard.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/campaign-execution-owner-drift-guard.js":
            self._static(path)
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
    print(f"BINARIO Marketing App · post-W99 Campaign Execution Owner Drift Guard: {url}")
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


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "annotate_campaign_execution_owner_drift", "create_server", "serve"]
