from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_existing_activity_reschedule_control_app as base


_RESULTS_ACTION_KINDS = {
    "capture_results",
    "review_coverage",
    "record_decision",
    "review_results",
}


class AppRuntime(base.AppRuntime):
    """Expose exact local campaign context for results-owner navigation only."""

    def campaign_results_owner_context(self, company_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        learning = self.learning_payload(company.id)
        intelligence = self.results_intelligence_workspace(company.id)

        learning_matches = [row for row in learning.get("campaigns") or [] if row.get("id") == campaign.id]
        if len(learning_matches) > 1:
            raise ValueError("campaign appears more than once in learning payload")
        learning_row = learning_matches[0] if learning_matches else None

        intelligence_matches = [row for row in intelligence.get("campaigns") or [] if (row.get("campaign") or {}).get("id") == campaign.id]
        if len(intelligence_matches) != 1:
            raise ValueError("campaign results context is not uniquely represented")
        intelligence_row = intelligence_matches[0]
        latest_snapshot = learning.get("latest_snapshot")
        ai = intelligence.get("ai") or {}

        return {
            "schema": "binario.marketing.campaign-results-owner-context.v1",
            "company": {"id": company.id, "name": company.name},
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "objective": campaign.objective,
                "status": campaign.status,
                "channels": list(campaign.channels),
            },
            "learning": {
                "latest_snapshot": None if latest_snapshot is None else {
                    "id": latest_snapshot.get("id"),
                    "created_at": latest_snapshot.get("created_at"),
                    "date_preset": latest_snapshot.get("date_preset"),
                    "coverage": latest_snapshot.get("coverage") or {},
                },
                "campaign_available": learning_row is not None,
                "campaign": learning_row,
            },
            "intelligence": {
                "evidence": intelligence_row.get("evidence") or {},
                "attribution": intelligence_row.get("attribution") or {},
                "decision": intelligence_row.get("decision"),
                "next_action": intelligence_row.get("next_action") or {},
                "requires_attention": bool(intelligence_row.get("requires_attention")),
            },
            "controls": {
                "capture_results": {
                    "owner": "W52_LEARNING_REFRESH",
                    "available": True,
                    "provider_read_requires_explicit_confirmation": True,
                    "automatic_provider_read": False,
                },
                "record_decision": {
                    "owner": "W52_DECISION_FORM",
                    "available": learning_row is not None,
                    "prepare_is_business_mutation": False,
                    "submit_requires_human_action": True,
                },
                "optional_ai": {
                    "owner": "W65_OPTIONAL_AI",
                    "available": bool((intelligence_row.get("evidence") or {}).get("has_signal") and ai.get("configured")),
                    "generation_requires_explicit_confirmation": True,
                    "marketing_execution_authority": False,
                },
            },
            "contracts": {
                "campaign_identity_is_exact": True,
                "owner_context_is_local_read_only": True,
                "learning_refresh_authority_remains_wave52": True,
                "decision_authority_remains_wave52": True,
                "optional_ai_authority_remains_wave65": True,
            },
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "business_mutation_performed": False,
                "ai_generation_performed": False,
                "automatic_execution": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Add one local GET context projection and browser owner-handoff adapter."""

    def _campaign_results_owner_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/activity-reschedule-control.js":
            target = self.server.runtime.repo_root / "web" / "activity-reschedule-control.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CampaignResultsOwnerAfterActivityReschedule(){
  if(document.querySelector('script[data-post-w99-campaign-results-owner]'))return;
  const script=document.createElement('script');
  script.src='/campaign-results-owner-handoff.js';
  script.defer=true;
  script.dataset.postW99CampaignResultsOwner='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/campaign-results-owner-handoff.js":
            target = self.server.runtime.repo_root / "web" / "campaign-results-owner-handoff.js"
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
        if path == "/campaign-results-owner-handoff.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "campaigns"
                and parts[5] == "results-owner-context"
            ):
                self._json(self.server.runtime.campaign_results_owner_context(parts[2], parts[4]))
                return
        except Exception as exc:
            self._campaign_results_owner_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Campaign Results Owner Handoff: {url}")
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


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
