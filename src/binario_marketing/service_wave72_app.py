from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from . import service_wave71_app as base


REQUIRED_WEB_ASSETS = (
    "app.js", "pro-media.js", "visual-timeline.js", "transcription.js", "clipper-modes.js",
    "social.js", "social-uat.js", "instagram-local-reel.js", "operational-readiness.js",
    "marketing-ops.js", "crm.js", "company-content.js", "campaigns.js", "audiences.js",
    "contactability.js", "analytics.js", "inbox.js", "inbox-replies.js", "editorial-management.js",
    "daily-ops.js", "daily-actions.js", "followup-reschedule.js", "product-shell.js",
    "paid-media-center.js", "creative-studio.js", "command-center.js", "ai-copilot.js",
    "learning-loop.js", "attribution-foundation.js", "capture-bridge.js", "lead-intake.js",
    "public-gateway.js", "local-product-integration.js", "workdesk.js", "commercial-desk.js",
    "contact-360.js", "commercial-pipeline.js", "execution-workspace.js", "results-intelligence.js",
    "uat-readiness.js", "physical-uat.js", "guided-physical-uat.js", "physical-uat-preflight.js",
    "release-evidence.js", "candidate-certification-dossier.js", "product-entry.js",
)

REQUIRED_RUNTIME_METHODS = (
    "companies_payload", "create_company", "company_detail", "contacts_payload", "create_contact",
    "opportunities_payload", "create_opportunity", "activities_payload", "create_activity",
    "company_media_payload", "campaigns_payload", "create_campaign", "audiences_payload",
    "create_audience", "company_workspace_summary", "company_paid_media", "company_creatives_payload",
    "marketing_command_center", "ai_settings_payload", "learning_payload", "attribution_payload",
    "capture_bridge_payload", "lead_intake_payload", "daily_workdesk", "commercial_desk",
    "commercial_pipeline", "campaign_execution_workspace", "results_intelligence_workspace",
    "product_uat_readiness", "physical_uat_overview", "physical_uat_preflight", "release_evidence",
    "candidate_certification_dossier",
)

SAFE_COMPANY_PROJECTIONS = (
    "company_detail", "ops_dashboard", "contacts_payload", "opportunities_payload", "activities_payload",
    "company_media_payload", "campaigns_payload", "audiences_payload", "company_workspace_summary",
    "company_paid_media", "company_creatives_payload", "marketing_command_center", "ai_settings_payload",
    "learning_payload", "attribution_payload", "capture_bridge_payload", "lead_intake_payload",
    "daily_workdesk", "commercial_desk", "commercial_pipeline", "campaign_execution_workspace",
    "results_intelligence_workspace", "product_uat_readiness", "physical_uat_overview",
    "physical_uat_preflight", "release_evidence", "candidate_certification_dossier",
)


class AppRuntime(base.AppRuntime):
    """Wave 72 makes product entry and company-scoped journey integrity explicit and testable."""

    def product_integrity(self, company_id: str | None = None) -> dict:
        web_root = self.repo_root / "web"
        assets = [
            {"name": name, "present": (web_root / name).is_file()}
            for name in REQUIRED_WEB_ASSETS
        ]
        methods = [
            {"name": name, "implemented": callable(getattr(self, name, None))}
            for name in REQUIRED_RUNTIME_METHODS
        ]
        apps = list(self.apps_payload())
        projections: list[dict] = []
        company = None
        if company_id:
            company = self.companies.get(company_id)
            for name in SAFE_COMPANY_PROJECTIONS:
                try:
                    getattr(self, name)(company.id)
                except Exception as exc:
                    projections.append({"name": name, "status": "FAIL", "error": f"{type(exc).__name__}: {exc}"})
                else:
                    projections.append({"name": name, "status": "PASS", "error": None})

        missing_assets = [row["name"] for row in assets if not row["present"]]
        missing_methods = [row["name"] for row in methods if not row["implemented"]]
        failed_projections = [row["name"] for row in projections if row["status"] != "PASS"]
        ready = not missing_assets and not missing_methods and not failed_projections
        return {
            "schema": "binario.marketing.product-integrity.v1",
            "ready": ready,
            "company": {"id": company.id, "name": company.name} if company else None,
            "entrypoint": {
                "deterministic_boot": True,
                "script": "/product-entry.js",
                "company_onboarding_required": True,
                "company_change_events": True,
                "refresh_events": True,
            },
            "inventory": {
                "required_web_assets": len(assets),
                "present_web_assets": len(assets) - len(missing_assets),
                "required_runtime_methods": len(methods),
                "implemented_runtime_methods": len(methods) - len(missing_methods),
                "registered_apps": len(apps),
                "company_projection_checks": len(projections),
                "company_projection_pass": len(projections) - len(failed_projections),
            },
            "missing": {
                "web_assets": missing_assets,
                "runtime_methods": missing_methods,
                "failed_company_projections": failed_projections,
            },
            "assets": assets,
            "runtime_methods": methods,
            "company_projections": projections,
            "apps": [{"id": row.get("id"), "name": row.get("name"), "status": row.get("status")} for row in apps],
            "safety": {
                "read_only": True,
                "provider_mutation_performed": False,
                "marketing_mutation_performed": False,
                "release_mutation_performed": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/product-entry.js":
            self._static(path)
            return
        if path == "/api/product-integrity":
            try:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.product_integrity(company_id))
            except Exception as exc:
                self._wave67_error(exc)
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
    print(f"BINARIO Marketing App: {url}")
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
