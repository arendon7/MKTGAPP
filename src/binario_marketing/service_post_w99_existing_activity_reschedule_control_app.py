from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .post_w99_crm_activity_store import PostW99ActivityCRMStore
from . import service_post_w99_opportunity_followup_control_app as base


_ACTIVITY_PIPELINE_KINDS = {
    "pipeline_overdue_followup",
    "pipeline_unscheduled_followup",
}


def _text(value: object) -> str:
    return str(value or "").strip()


def _pipeline_cards(pipeline: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for lane in pipeline.get("lanes") or []:
        for row in lane.get("opportunities") or []:
            opportunity_id = _text(row.get("id"))
            if opportunity_id:
                result[opportunity_id] = row
    return result


def _copy_routed_rows(payload: dict, routed: dict[str, dict]) -> None:
    if payload.get("next_action"):
        action_id = _text(payload["next_action"].get("id"))
        if action_id in routed:
            payload["next_action"] = routed[action_id]
    focus = payload.get("focus") or {}
    for lane in ("now", "next", "later"):
        focus[lane] = [routed.get(_text(row.get("id")), row) for row in focus.get(lane) or []]
    payload["focus"] = focus


class AppRuntime(base.AppRuntime):
    """Post-W99 terminal adding exact rescheduling of existing CRM activities."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.crm = PostW99ActivityCRMStore(runtime.crm.root)
        return runtime

    def reschedule_activity(self, company_id: str, activity_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        before = self.crm.get_activity(activity_id)
        if before.company_id != company.id:
            raise KeyError(activity_id)
        row = self.crm.reschedule_activity(company.id, activity_id, payload)
        if before.due_at != row.due_at:
            self.workspace.registries.timeline.append("crm.activity.rescheduled", {
                "company_id": company.id,
                "activity_id": row.id,
                "contact_id": row.contact_id,
                "opportunity_id": row.opportunity_id,
                "due_at_from": before.due_at,
                "due_at_to": row.due_at,
            })
        return asdict(row)

    def _exact_pending_activity(self, company_id: str, opportunity_id: str, activity_id: object):
        activity_id = _text(activity_id)
        if not activity_id:
            return None
        try:
            row = self.crm.get_activity(activity_id)
        except KeyError:
            return None
        if row.company_id != company_id or row.opportunity_id != opportunity_id or row.completed_at:
            return None
        return row

    def _pipeline_activity_owner(self, company_id: str, action: dict, card: dict | None):
        if not card:
            return None
        kind = _text(action.get("kind")).lower()
        opportunity_id = _text((action.get("action") or {}).get("opportunity_id"))
        if not opportunity_id:
            return None
        followup = card.get("followup") or {}

        if kind in _ACTIVITY_PIPELINE_KINDS:
            return self._exact_pending_activity(company_id, opportunity_id, followup.get("next_activity_id"))

        if kind != "pipeline_due_soon":
            return None
        due_at = _text(action.get("due_at"))
        if not due_at:
            return None
        # DUE_SOON can originate from next_action_at, an activity, or both. Route
        # to ACTIVITY only when the local CRM proves one unique pending activity
        # owns that timestamp and next_action_at does not share it.
        if _text(card.get("next_action_at")) == due_at:
            return None
        matches = [
            row for row in self.crm.list_activities(company_id, opportunity_id=opportunity_id)
            if not row.completed_at and _text(row.due_at) == due_at
        ]
        if len(matches) != 1:
            return None
        return matches[0]

    def action_center(self, company_id: str) -> dict:
        payload = deepcopy(super().action_center(company_id))
        cards = _pipeline_cards(self.commercial_pipeline(company_id))
        routed: dict[str, dict] = {}
        for row in payload.get("queue") or []:
            action_id = _text(row.get("id"))
            action = row.get("action") or {}
            opportunity_id = _text(action.get("opportunity_id"))
            activity = self._pipeline_activity_owner(company_id, row, cards.get(opportunity_id))
            if activity is not None:
                action["view"] = "crm"
                action["tab"] = "followups"
                action["entity_id"] = activity.id
                action["label"] = "Abrir seguimiento exacto"
                row["action"] = action
                row["due_at"] = activity.due_at
                row["owner_resolution"] = {
                    "target_kind": "ACTIVITY",
                    "activity_id": activity.id,
                    "method": "EXACT_LOCAL_ID",
                }
            if action_id:
                routed[action_id] = row
        payload["queue"] = [routed.get(_text(row.get("id")), row) for row in payload.get("queue") or []]
        _copy_routed_rows(payload, routed)
        contracts = dict(payload.get("contracts") or {})
        contracts.update({
            "pipeline_activity_owner_requires_exact_id": True,
            "pipeline_due_soon_activity_owner_requires_unique_source": True,
            "activity_owner_routing_does_not_reprioritize": True,
        })
        payload["contracts"] = contracts
        return payload


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds one narrow local PATCH and the corresponding browser owner control."""

    def _activity_reschedule_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/opportunity-followup-control.js":
            target = self.server.runtime.repo_root / "web" / "opportunity-followup-control.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99ActivityRescheduleAfterOpportunityControl(){
  if(document.querySelector('script[data-post-w99-activity-reschedule-control]'))return;
  const script=document.createElement('script');
  script.src='/activity-reschedule-control.js';
  script.defer=true;
  script.dataset.postW99ActivityRescheduleControl='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/activity-reschedule-control.js":
            target = self.server.runtime.repo_root / "web" / "activity-reschedule-control.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/activity-reschedule-control.js":
            self._static(parsed.path)
            return
        super().do_GET()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "activities":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.reschedule_activity(parts[2], parts[4], self._body()))
                return
        except Exception as exc:
            self._activity_reschedule_error(exc)
            return
        super().do_PATCH()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App · post-W99 Existing Activity Reschedule Control: {url}")
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
    "create_server",
    "serve",
]
