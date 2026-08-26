from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_campaign_execution_owner_cardinality_hardening_app as base


def _is_planned_only_observation(row: dict) -> bool:
    """Return True only for the canonical campaign PLANNED_ONLY projection."""
    return (
        str(row.get("source") or "").upper() == "CAMPAIGN"
        and str(row.get("kind") or "").lower() == "planned_only"
    )


def _focus_from_queue(queue: list[dict]) -> dict:
    return {
        "now": [row for row in queue if str(row.get("urgency") or "").upper() in {"CRITICAL", "HIGH"}][:8],
        "next": [row for row in queue if str(row.get("urgency") or "").upper() == "MEDIUM"][:8],
        "later": [row for row in queue if str(row.get("urgency") or "").upper() == "LOW"][:8],
    }


def preserve_planned_only_actionability(payload: dict) -> dict:
    """Separate non-executable PLANNED_ONLY campaign state from the action queue."""
    result = deepcopy(payload)
    inherited_queue = list(result.get("queue") or [])
    actionable: list[dict] = []
    planned_only: list[dict] = []

    for row in inherited_queue:
        if not _is_planned_only_observation(row):
            actionable.append(row)
            continue
        observation = deepcopy(row)
        observation["requires_human_action"] = False
        observation["read_only_recommendation"] = True
        observation["blocking"] = False
        observation["actionability"] = {
            "state": "NON_ACTIONABLE",
            "executable": False,
            "today_eligible": False,
            "reason_code": "W64_PLANNED_ONLY",
            "reason": (
                "Wave64 declaró esta campaña como PLANNED_ONLY y requires_action=False; "
                "este gate no tiene provider de ejecución para convertir el canal planificado en una tarea."
            ),
            "owner_navigation_allowed": True,
        }
        planned_only.append(observation)

    existing_observations = list(result.get("observations") or [])
    existing_ids = {str(row.get("id") or "") for row in existing_observations}
    for row in planned_only:
        if str(row.get("id") or "") not in existing_ids:
            existing_observations.append(row)
            existing_ids.add(str(row.get("id") or ""))

    result["queue"] = actionable
    result["next_action"] = actionable[0] if actionable else None
    result["focus"] = _focus_from_queue(actionable)
    result["observations"] = existing_observations

    urgency_counts = {key: 0 for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    source_counts = {key: 0 for key in ("OPERATIONS", "COMMERCIAL", "CAMPAIGN", "SETUP")}
    for row in actionable:
        urgency = str(row.get("urgency") or "").upper()
        source = str(row.get("source") or "OTHER").upper()
        if urgency in urgency_counts:
            urgency_counts[urgency] += 1
        source_counts[source] = source_counts.get(source, 0) + 1

    summary = dict(result.get("summary") or {})
    summary.update({
        "queue_total": len(actionable),
        "blocking": sum(1 for row in actionable if row.get("blocking")),
        "critical": urgency_counts["CRITICAL"],
        "high": urgency_counts["HIGH"],
        "medium": urgency_counts["MEDIUM"],
        "low": urgency_counts["LOW"],
        "by_source": source_counts,
        "campaign_actions": sum(1 for row in actionable if str(row.get("source") or "").upper() == "CAMPAIGN"),
        "observations_total": len(existing_observations),
        "campaign_observations": sum(
            1 for row in existing_observations if _is_planned_only_observation(row)
        ),
    })
    result["summary"] = summary

    contracts = dict(result.get("contracts") or {})
    contracts.update({
        "planned_only_is_observational": True,
        "planned_only_excluded_from_action_queue": True,
        "planned_only_excluded_from_today": True,
        "canonical_action_order_preserved_after_filter": True,
        "no_provider_capability_invented": True,
    })
    result["contracts"] = contracts
    return result


class AppRuntime(base.AppRuntime):
    """Preserve W64 PLANNED_ONLY semantics after the full post-W99 owner chain."""

    def action_center(self, company_id: str) -> dict:
        return preserve_planned_only_actionability(super().action_center(company_id))


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Load the zero-transport observation adapter after owner-cardinality hardening."""

    def _static(self, path: str) -> None:
        if path == "/campaign-execution-owner-cardinality-hardening.js":
            target = self.server.runtime.repo_root / "web" / "campaign-execution-owner-cardinality-hardening.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PlannedOnlyActionabilityPreservation(){
  if(document.querySelector('script[data-post-w99-planned-only-actionability]'))return;
  const script=document.createElement('script');
  script.src='/planned-only-actionability.js';
  script.defer=true;
  script.dataset.postW99PlannedOnlyActionability='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/planned-only-actionability.js":
            target = self.server.runtime.repo_root / "web" / "planned-only-actionability.js"
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
        if path == "/planned-only-actionability.js":
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
    print(f"BINARIO Marketing App · post-W99 Planned-Only Actionability Preservation: {url}")
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
    "_is_planned_only_observation",
    "create_server",
    "preserve_planned_only_actionability",
    "serve",
]
