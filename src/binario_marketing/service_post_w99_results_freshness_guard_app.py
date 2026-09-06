from __future__ import annotations

from pathlib import Path

from . import service_post_w99_inbox_crm_identity_app as base
from .results_freshness import apply_results_decision_freshness, campaign_decision_refresh_required


class AppRuntime(base.AppRuntime):
    """Require a recent explicit results snapshot before new decisions or campaign AI."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def results_intelligence_workspace(self, company_id: str) -> dict:
        return apply_results_decision_freshness(super().results_intelligence_workspace(company_id))

    def _assert_campaign_decision_fresh(self, company_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        self.campaigns.get_for_company(company.id, campaign_id)
        payload = self.results_intelligence_workspace(company.id)
        required, freshness = campaign_decision_refresh_required(payload, campaign_id)
        if required:
            raise ValueError(
                "actualiza los resultados de esta campaña antes de registrar una nueva decisión o pedir análisis IA"
            )
        return freshness

    def record_learning_decision(self, company_id: str, payload: dict) -> dict:
        if isinstance(payload, dict):
            kind = str(payload.get("entity_kind") or "").strip().upper()
            entity_id = str(payload.get("entity_id") or "").strip()
            if kind == "CAMPAIGN" and entity_id:
                self._assert_campaign_decision_fresh(company_id, entity_id)
        return super().record_learning_decision(company_id, payload)

    def generate_ai_copilot(self, company_id: str, payload: dict) -> dict:
        if isinstance(payload, dict):
            task = str(payload.get("task") or "STRATEGY").strip().upper()
            campaign_id = str(payload.get("campaign_id") or "").strip()
            if task == "CAMPAIGN" and campaign_id:
                self._assert_campaign_decision_fresh(company_id, campaign_id)
        return super().generate_ai_copilot(company_id, payload)

    def campaign_results_owner_context(self, company_id: str, campaign_id: str) -> dict:
        context = super().campaign_results_owner_context(company_id, campaign_id)
        intelligence = context.get("intelligence") or {}
        evidence = intelligence.get("evidence") or {}
        freshness = evidence.get("operational_freshness") or {}
        refresh_required = bool(freshness.get("decision_refresh_required"))
        controls = context.get("controls") or {}
        record = controls.get("record_decision") or {}
        optional_ai = controls.get("optional_ai") or {}
        if refresh_required:
            record["available"] = False
            record["blocked_reason"] = "RESULTS_REFRESH_REQUIRED"
            optional_ai["available"] = False
            optional_ai["blocked_reason"] = "RESULTS_REFRESH_REQUIRED"
        controls["record_decision"] = record
        controls["optional_ai"] = optional_ai
        context["controls"] = controls
        context["freshness_guard"] = {
            "refresh_required": refresh_required,
            "state": freshness.get("state"),
            "age_seconds": freshness.get("age_seconds"),
            "max_age_seconds": freshness.get("max_age_seconds"),
            "generic_business_staleness_judgment": False,
            "provider_refresh_automatic": False,
        }
        contracts = context.get("contracts") or {}
        contracts["active_campaign_decision_freshness_guard"] = True
        contracts["historical_evidence_remains_readable"] = True
        context["contracts"] = contracts
        return context


MarketingHTTPServer = base.MarketingHTTPServer
MarketingHandler = base.MarketingHandler


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    print(f"BINARIO Marketing App · post-W99 Results Freshness Guard: http://{actual_host}:{actual_port}/")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{actual_host}:{actual_port}/")
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
