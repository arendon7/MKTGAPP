from __future__ import annotations

from http import HTTPStatus
from urllib.parse import urlparse

from . import service_wave75_app as base


def _checkpoint(
    code: str,
    label: str,
    view: str,
    status: str,
    detail: str,
    expected: str,
    *,
    required: bool,
    tab: str | None = None,
) -> dict:
    return {
        "code": code,
        "label": label,
        "view": view,
        "tab": tab,
        "status": status,
        "detail": detail,
        "expected": expected,
        "required": required,
    }


class AppRuntime(base.AppRuntime):
    """Wave 76 observes real operator progress through the isolated W75 sandbox."""

    def uat_sandbox_journey(self) -> dict:
        sandbox = self.uat_sandbox_status()
        manifest = self.uat_sandbox.current()
        company = sandbox.get("company") or {}
        company_id = str(company.get("id") or "")

        if not sandbox.get("exists") or not company_id:
            return {
                "schema": "binario.marketing.uat-sandbox-journey.v1",
                "sandbox": sandbox,
                "summary": {
                    "core_required": 0,
                    "core_verified": 0,
                    "core_complete": False,
                    "optional_verified": 0,
                    "optional_total": 0,
                },
                "next_checkpoint": None,
                "checkpoints": [],
                "safety": {
                    "read_only_projection": True,
                    "business_mutation_performed": False,
                    "provider_read_performed": False,
                    "provider_mutation_performed": False,
                    "physical_uat_evidence_recorded": False,
                    "background_polling": False,
                    "cloud_required": False,
                },
            }

        if not sandbox.get("active"):
            return {
                "schema": "binario.marketing.uat-sandbox-journey.v1",
                "sandbox": sandbox,
                "summary": {
                    "core_required": 0,
                    "core_verified": 0,
                    "core_complete": False,
                    "optional_verified": 0,
                    "optional_total": 0,
                },
                "next_checkpoint": None,
                "checkpoints": [],
                "safety": {
                    "read_only_projection": True,
                    "business_mutation_performed": False,
                    "provider_read_performed": False,
                    "provider_mutation_performed": False,
                    "physical_uat_evidence_recorded": False,
                    "background_polling": False,
                    "cloud_required": False,
                },
            }

        entities = dict((manifest or {}).get("entities") or {})
        intake = self.lead_intake_payload(company_id)
        leads = {str(row.get("id") or ""): row for row in intake.get("leads") or []}
        matched = leads.get(str(entities.get("matched_lead_id") or ""))
        new_lead = leads.get(str(entities.get("new_lead_id") or ""))

        opportunities = {row.id: row for row in self.crm.list_opportunities(company_id)}
        activities = {row.id: row for row in self.crm.list_activities(company_id)}
        campaigns = {row.id: row for row in self.campaigns.list(company_id)}
        opportunity = opportunities.get(str(entities.get("opportunity_id") or ""))
        activity = activities.get(str(entities.get("activity_id") or ""))
        campaign = campaigns.get(str(entities.get("campaign_id") or ""))

        execution = self.campaign_execution_workspace(company_id)
        execution_row = next(
            (
                row for row in execution.get("campaigns") or []
                if str((row.get("campaign") or {}).get("id") or "") == str(entities.get("campaign_id") or "")
            ),
            None,
        )
        results = self.results_intelligence_workspace(company_id)
        results_row = next(
            (
                row for row in results.get("campaigns") or []
                if str((row.get("campaign") or {}).get("id") or "") == str(entities.get("campaign_id") or "")
            ),
            None,
        )

        matched_status = str((matched or {}).get("status") or "MISSING")
        new_status = str((new_lead or {}).get("status") or "MISSING")
        stage_changed = bool(opportunity is not None and opportunity.stage != "PROPOSAL")
        followup_changed = bool(
            activity is not None
            and (activity.completed_at is not None or activity.updated_at != activity.created_at)
        )
        campaign_present = campaign is not None and campaign.status == "IN_PROGRESS"

        creative_total = int(((execution_row or {}).get("creative") or {}).get("total") or 0)
        organic = (execution_row or {}).get("organic") or {}
        organic_counts = organic.get("counts") or {}
        paid = (execution_row or {}).get("paid") or {}
        distribution_total = (
            int(organic.get("publications") or 0)
            + int(paid.get("plans") or 0)
        )
        distributed = bool(
            int(organic_counts.get("QUEUED") or 0)
            or int(organic_counts.get("PUBLISHED") or 0)
            or int(paid.get("plans") or 0)
        )
        has_results = bool(
            results.get("latest_snapshot")
            and results_row
            and (results_row.get("evidence") or {}).get("has_signal")
        )
        has_ai = bool(results_row and results_row.get("latest_ai"))

        checkpoints = [
            _checkpoint(
                "FIXTURE_INTEGRITY",
                "Sandbox íntegro",
                "uat-readiness",
                "VERIFIED" if sandbox.get("functional_ready") else "BROKEN",
                "Las seis entidades sintéticas canónicas siguen presentes." if sandbox.get("functional_ready") else "El fixture perdió una o más entidades; recrea el sandbox antes de seguir.",
                "Fixture activo, aislado y sin autoridad de release.",
                required=True,
            ),
            _checkpoint(
                "EXACT_MATCH_HANDOFF",
                "Resolver lead con coincidencia exacta",
                "commercial-desk",
                "VERIFIED" if matched_status == "CONVERTED" else "READY_TO_TEST" if matched_status == "MATCHED" else "NEEDS_REVIEW",
                f"Estado actual del lead exacto: {matched_status}.",
                "El operador vincula explícitamente la coincidencia exacta; nunca fuzzy ni auto-conversión.",
                required=True,
            ),
            _checkpoint(
                "NEW_LEAD_HANDOFF",
                "Convertir lead nuevo",
                "commercial-desk",
                "VERIFIED" if new_status == "CONVERTED" else "READY_TO_TEST" if new_status in {"NEW", "UNIDENTIFIED"} else "NEEDS_REVIEW",
                f"Estado actual del lead nuevo: {new_status}.",
                "El operador crea el contacto de forma explícita desde Lead Intake/Mesa comercial.",
                required=True,
            ),
            _checkpoint(
                "PIPELINE_STAGE_SAVE",
                "Guardar un cambio de etapa",
                "crm",
                "VERIFIED" if stage_changed else "READY_TO_TEST" if opportunity is not None else "BROKEN",
                f"Etapa actual: {opportunity.stage if opportunity is not None else 'MISSING'}.",
                "Cambiar el selector no basta: la nueva etapa queda persistida solo tras Guardar etapa.",
                required=True,
                tab="pipeline",
            ),
            _checkpoint(
                "FOLLOWUP_INTERACTION",
                "Completar o reprogramar seguimiento",
                "crm",
                "VERIFIED" if followup_changed else "READY_TO_TEST" if activity is not None else "BROKEN",
                (
                    "El seguimiento sintético ya fue modificado explícitamente."
                    if followup_changed
                    else "El seguimiento conserva exactamente su estado inicial."
                ),
                "Completar o reprogramar reutiliza las rutas CRM certificadas y deja evidencia local durable.",
                required=True,
                tab="followups",
            ),
            _checkpoint(
                "CAMPAIGN_CONTEXT",
                "Campaña controlada disponible",
                "campaigns",
                "VERIFIED" if campaign_present else "BROKEN",
                "Campaña LEADS sintética activa." if campaign_present else "La campaña sintética esperada no está activa.",
                "La campaña conserva contexto de empresa y audiencia sin provider action.",
                required=True,
            ),
            _checkpoint(
                "CREATIVE_HANDOFF",
                "Campaña → Creative Studio",
                "execution",
                "VERIFIED" if creative_total > 0 else "OPTIONAL_READY",
                f"Creativos vinculados a la campaña: {creative_total}.",
                "Crear/vincular una pieza debe ocurrir desde el módulo canónico; el validador nunca la genera.",
                required=False,
            ),
            _checkpoint(
                "DISTRIBUTION_HANDOFF",
                "Campaña → distribución preparada",
                "execution",
                "VERIFIED" if distributed else "OPTIONAL_READY",
                f"Salidas locales detectadas: {distribution_total}.",
                "Una publicación preparada o plan de pauta local demuestra el handoff; activar provider no es necesario.",
                required=False,
            ),
            _checkpoint(
                "RESULTS_EVIDENCE",
                "Resultados observados",
                "intelligence",
                "VERIFIED" if has_results else "EXTERNAL_OPTIONAL",
                "Existe evidencia observada para la campaña." if has_results else "W75 no siembra métricas ni evidencia provider; este tramo espera captura explícita real.",
                "Métricas reales y atribución permanecen separadas; nunca se inventan para completar el sandbox.",
                required=False,
            ),
            _checkpoint(
                "AI_INTERPRETATION",
                "Interpretación IA opcional",
                "intelligence",
                "VERIFIED" if has_ai else "EXTERNAL_OPTIONAL",
                "Existe un análisis IA explícito para la campaña." if has_ai else "No hay análisis IA y no es requisito del core funcional.",
                "IA solo después de evidencia suficiente y confirmación explícita; nunca ejecuta acciones.",
                required=False,
            ),
        ]

        required = [row for row in checkpoints if row["required"]]
        optional = [row for row in checkpoints if not row["required"]]
        required_verified = [row for row in required if row["status"] == "VERIFIED"]
        optional_verified = [row for row in optional if row["status"] == "VERIFIED"]
        next_checkpoint = next((row for row in required if row["status"] != "VERIFIED"), None)
        if next_checkpoint is None:
            next_checkpoint = next((row for row in optional if row["status"] not in {"VERIFIED", "EXTERNAL_OPTIONAL"}), None)

        return {
            "schema": "binario.marketing.uat-sandbox-journey.v1",
            "sandbox": sandbox,
            "summary": {
                "core_required": len(required),
                "core_verified": len(required_verified),
                "core_complete": len(required_verified) == len(required),
                "optional_verified": len(optional_verified),
                "optional_total": len(optional),
            },
            "next_checkpoint": next_checkpoint,
            "checkpoints": checkpoints,
            "contracts": {
                "state_observation_only": True,
                "automatic_pass_recording": False,
                "automatic_business_action": False,
                "physical_release_evidence_allowed": False,
                "provider_evidence_seeded": False,
                "results_evidence_seeded": False,
            },
            "safety": {
                "read_only_projection": True,
                "business_mutation_performed": False,
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "physical_uat_evidence_recorded": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 76 adds only journey observation and browser guidance."""

    def _static(self, path: str) -> None:
        if path == "/uat-sandbox.js":
            target = self.server.runtime.repo_root / "web" / "uat-sandbox.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave76SandboxFunctionalJourney(){
  if(document.querySelector('script[data-uat-functional-journey-wave76]'))return;
  const journey=document.createElement('script');
  journey.src='/uat-functional-journey.js';
  journey.defer=true;
  journey.dataset.uatFunctionalJourneyWave76='1';
  document.head.append(journey);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/uat-functional-journey.js":
            self._static(path)
            return
        if path == "/api/uat-sandbox/journey":
            try:
                self._json(self.server.runtime.uat_sandbox_journey())
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
