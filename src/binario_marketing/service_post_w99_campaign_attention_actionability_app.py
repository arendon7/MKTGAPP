from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_post_w99_campaign_coordinate_actionability_app as base


_SCHEMA = "binario.marketing.campaign-attention-actionability.v1"
_PASSIVE_CODES = {"CALENDAR", "REVIEW_RESULTS", "OPTIONAL_AI"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _focus_from_queue(queue: list[dict]) -> dict:
    return {
        "now": [row for row in queue if _text(row.get("urgency")).upper() in {"CRITICAL", "HIGH"}][:8],
        "next": [row for row in queue if _text(row.get("urgency")).upper() == "MEDIUM"][:8],
        "later": [row for row in queue if _text(row.get("urgency")).upper() == "LOW"][:8],
    }


def _campaign_passive_lineage(row: dict, intelligence: dict) -> dict | None:
    """Prove canonical non-action lineage without guessing from presentation fields."""
    if _text(row.get("source")).upper() != "CAMPAIGN":
        return None
    code = _text(row.get("kind")).upper()
    if code not in _PASSIVE_CODES:
        return None
    campaign_id = _text((row.get("action") or {}).get("campaign_id"))
    if not campaign_id:
        return None

    matches = [
        card for card in (intelligence.get("campaigns") or [])
        if _text((card.get("campaign") or {}).get("id")) == campaign_id
    ]
    if len(matches) != 1 or not isinstance(matches[0], dict):
        return None
    card = matches[0]
    if _text((card.get("next_action") or {}).get("code")).upper() != code:
        return None
    # Exact False is required. Missing/falsy data cannot hide existing work.
    if card.get("requires_attention") is not False:
        return None

    if code == "CALENDAR":
        execution = card.get("execution") or {}
        if _text((execution.get("next_action") or {}).get("code")).upper() != "CALENDAR":
            return None
        if execution.get("requires_action") is not False:
            return None
        source = "W65_FALLBACK_TO_W64"
        w64_requires_action: bool | None = False
    else:
        source = "W65_RESULTS_INTELLIGENCE"
        w64_requires_action = None

    return {
        "schema": _SCHEMA,
        "source": source,
        "campaign_id": campaign_id,
        "code": code,
        "w65_requires_attention": False,
        "w64_requires_action": w64_requires_action,
    }


def _observation_copy(row: dict, lineage: dict) -> dict:
    observation = deepcopy(row)
    code = _text(lineage.get("code")).upper() or _text(row.get("kind")).upper()
    observation["requires_human_action"] = False
    observation["blocking"] = False
    observation["read_only_recommendation"] = True
    observation["actionability"] = {
        "schema": _SCHEMA,
        "state": "NON_REQUIRED_CAMPAIGN_ATTENTION",
        "executable": False,
        "today_eligible": False,
        "owner_navigation_allowed": True,
        "reason_code": f"CAMPAIGN_{code}_SOURCE_NOT_REQUIRING_ACTION",
        "reason": (
            "La fuente canónica conserva esta superficie como contexto opcional u observacional "
            "y declara explícitamente que no requiere acción humana. Action Center mantiene la "
            "navegación al owner existente, pero la excluye de la cola y de Hoy."
        ),
        "lineage": deepcopy(lineage),
    }
    return observation


def preserve_campaign_attention_actionability(payload: dict, intelligence: dict) -> dict:
    """Demote only campaign rows whose non-actionability has exact canonical lineage."""
    result = deepcopy(payload)
    inherited_queue = list(result.get("queue") or [])
    actionable: list[dict] = []
    passive_observations: list[dict] = []

    for row in inherited_queue:
        lineage = _campaign_passive_lineage(row, intelligence)
        if lineage is None:
            actionable.append(row)
        else:
            passive_observations.append(_observation_copy(row, lineage))

    existing_observations = list(result.get("observations") or [])
    existing_ids = {_text(row.get("id")) for row in existing_observations}
    for row in passive_observations:
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
    summary.update({
        "queue_total": len(actionable),
        "blocking": sum(1 for row in actionable if row.get("blocking")),
        "critical": urgency_counts["CRITICAL"],
        "high": urgency_counts["HIGH"],
        "medium": urgency_counts["MEDIUM"],
        "low": urgency_counts["LOW"],
        "by_source": source_counts,
        "campaign_actions": sum(1 for row in actionable if _text(row.get("source")).upper() == "CAMPAIGN"),
        "observations_total": len(existing_observations),
        "campaign_observations": summary.get("campaign_observations", 0),
        "coordinate_observations": summary.get("coordinate_observations", 0),
        "coordinate_exact_recovery_actions": summary.get("coordinate_exact_recovery_actions", 0),
        "campaign_attention_observations": sum(
            1 for row in existing_observations
            if (row.get("actionability") or {}).get("state") == "NON_REQUIRED_CAMPAIGN_ATTENTION"
        ),
    })
    result["summary"] = summary

    contracts = dict(result.get("contracts") or {})
    contracts.update({
        "campaign_passive_attention_uses_exact_source_lineage": True,
        "calendar_requires_w64_and_w65_non_action_truth": True,
        "results_review_and_optional_ai_follow_w65_attention_truth": True,
        "passive_campaign_states_excluded_from_today": True,
        "passive_lineage_mismatch_preserves_existing_action": True,
        "campaign_attention_action_order_preserved_after_filter": True,
        "campaign_attention_actionability_is_read_only": True,
    })
    result["contracts"] = contracts
    return result


class AppRuntime(base.AppRuntime):
    """Preserve canonical campaign attention semantics after coordinate actionability."""

    def action_center(self, company_id: str) -> dict:
        inherited = super().action_center(company_id)
        intelligence = self.results_intelligence_workspace(company_id)
        return preserve_campaign_attention_actionability(inherited, intelligence)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Render proven passive campaign observations after coordinate actionability."""

    def _static(self, path: str) -> None:
        if path == "/campaign-coordinate-actionability.js":
            target = self.server.runtime.repo_root / "web" / "campaign-coordinate-actionability.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignAttentionActionabilityPreservation(){
  if(document.querySelector('script[data-post-w99-campaign-attention-actionability]'))return;
  const script=document.createElement('script');
  script.src='/campaign-attention-actionability.js';
  script.defer=true;
  script.dataset.postW99CampaignAttentionActionability='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/campaign-attention-actionability.js":
            target = self.server.runtime.repo_root / "web" / "campaign-attention-actionability.js"
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
        if path == "/campaign-attention-actionability.js":
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
    print(f"BINARIO Marketing App · post-W99 Campaign Attention Actionability Preservation: {url}")
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
    "_campaign_passive_lineage",
    "create_server",
    "preserve_campaign_attention_actionability",
    "serve",
]
