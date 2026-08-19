from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave65_app as base
from .version import RELEASE_READY, RELEASE_TAG, __version__


_CANONICAL_WORKFLOWS = {"ci.yml", "full-mac-app.yml", "persistent-release.yml"}


def _int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _step(
    code: str,
    label: str,
    view: str,
    status: str,
    detail: str,
    *,
    required: bool = True,
    metric: int | None = None,
    tab: str | None = None,
) -> dict:
    return {
        "code": code,
        "label": label,
        "view": view,
        "tab": tab,
        "status": status,
        "detail": detail,
        "required": required,
        "metric": metric,
    }


class AppRuntime(base.AppRuntime):
    """Wave 66 projects the certified local product into a manual-UAT readiness journey."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def product_uat_readiness(self, company_id: str) -> dict:
        company = self.companies.get(company_id)

        # Every composition below is local/read-only. If a certified surface cannot compose,
        # this endpoint fails rather than masking the product defect as a green UAT state.
        workdesk = self.daily_workdesk(company.id)
        commercial = self.commercial_desk(company.id)
        pipeline = self.commercial_pipeline(company.id)
        execution = self.campaign_execution_workspace(company.id)
        results = self.results_intelligence_workspace(company.id)

        workdesk_summary = workdesk.get("summary") or {}
        commercial_summary = commercial.get("summary") or {}
        pipeline_summary = pipeline.get("summary") or {}
        execution_summary = execution.get("summary") or {}
        results_summary = results.get("summary") or {}

        commercial_records = (
            _int(commercial_summary.get("open_leads"))
            + _int(commercial_summary.get("contacts"))
            + _int(commercial_summary.get("open_opportunities"))
        )
        active_campaigns = _int(execution_summary.get("active_campaigns"))
        prepared_distribution = (
            _int(execution_summary.get("queued_publications"))
            + _int(execution_summary.get("paid_remote_paused"))
        )
        published_distribution = sum(
            _int((row.get("organic") or {}).get("counts", {}).get("PUBLISHED"))
            for row in execution.get("campaigns") or []
        )
        has_distribution = prepared_distribution > 0 or published_distribution > 0
        latest_snapshot = results.get("latest_snapshot")
        observed_campaigns = _int(results_summary.get("with_observed_evidence"))
        attributed_campaigns = _int(results_summary.get("with_attributed_opportunities"))
        decision_campaigns = _int(results_summary.get("with_human_decision"))

        if commercial_records:
            commercial_status = "READY"
            commercial_detail = (
                f"{_int(commercial_summary.get('open_leads'))} lead(s) abiertos · "
                f"{_int(commercial_summary.get('open_opportunities'))} oportunidad(es) abiertas."
            )
        else:
            commercial_status = "NEEDS_DATA"
            commercial_detail = "Superficie lista; crea o importa un caso controlado para recorrer Inbox → Lead Intake → CRM."

        if active_campaigns:
            planning_status = "READY"
            planning_detail = f"{active_campaigns} campaña(s) activa(s) disponibles para el recorrido UAT."
        else:
            planning_status = "NEEDS_DATA"
            planning_detail = "Crea una campaña controlada para validar continuidad hacia Creative Studio y distribución."

        if prepared_distribution:
            distribution_status = "READY"
            distribution_detail = f"{prepared_distribution} salida(s) preparadas entre orgánico y pauta PAUSED."
        elif active_campaigns:
            distribution_status = "NEEDS_DATA"
            distribution_detail = "Hay campaña, pero falta preparar una publicación o un plan de pauta PAUSED para probar el handoff."
        else:
            distribution_status = "WAITING"
            distribution_detail = "Este tramo espera una campaña de prueba; no es un fallo de superficie."

        if latest_snapshot:
            learning_status = "READY"
            learning_detail = (
                f"Snapshot {latest_snapshot.get('date_preset') or 'local'} disponible · "
                f"{observed_campaigns} campaña(s) con evidencia observada · "
                f"{attributed_campaigns} con oportunidad atribuida."
            )
        elif has_distribution:
            learning_status = "NEEDS_EVIDENCE"
            learning_detail = "La distribución existe; captura resultados explícitamente antes de evaluar decisión o IA."
        else:
            learning_status = "WAITING"
            learning_detail = "Resultados espera distribución real o de prueba; no se inventan métricas para completar UAT."

        ai_configured = bool((results.get("ai") or {}).get("configured"))
        ai_detail = (
            "Provider/modelo configurado. La generación sigue siendo manual y sin autoridad de ejecución."
            if ai_configured
            else "IA no configurada. Es opcional para UAT funcional y no bloquea el core local."
        )

        journey = [
            _step(
                "COMPANY_CONTEXT",
                "Empresa y contexto",
                "home",
                "READY",
                f"Contexto activo: {company.name}. El cambio de empresa permanece explícito y persistente.",
            ),
            _step(
                "DAILY_DESK",
                "Hoy y prioridades",
                "home",
                "READY",
                f"{_int(workdesk_summary.get('attention'))} asunto(s) requieren atención en la mesa local.",
                metric=_int(workdesk_summary.get("attention")),
            ),
            _step(
                "COMMERCIAL_FLOW",
                "Inbox → Leads → CRM",
                "commercial-desk",
                commercial_status,
                commercial_detail,
                metric=commercial_records,
            ),
            _step(
                "PIPELINE",
                "Pipeline y seguimiento",
                "crm",
                "READY" if _int(pipeline_summary.get("open_opportunities")) else "NEEDS_DATA",
                (
                    f"{_int(pipeline_summary.get('open_opportunities'))} oportunidad(es) abiertas · "
                    f"{_int(pipeline_summary.get('requires_attention'))} requieren siguiente paso."
                    if _int(pipeline_summary.get("open_opportunities"))
                    else "Pipeline operativo listo; una oportunidad de prueba permite validar etapa y seguimiento explícitos."
                ),
                metric=_int(pipeline_summary.get("open_opportunities")),
                tab="pipeline",
            ),
            _step(
                "CAMPAIGN_PLANNING",
                "Planear campaña",
                "campaigns",
                planning_status,
                planning_detail,
                metric=active_campaigns,
            ),
            _step(
                "EXECUTION_HANDOFF",
                "Crear y distribuir",
                "execution",
                distribution_status,
                distribution_detail,
                metric=prepared_distribution,
            ),
            _step(
                "RESULTS_LEARNING",
                "Resultados y decisión",
                "intelligence",
                learning_status,
                learning_detail,
                metric=observed_campaigns + attributed_campaigns,
            ),
            _step(
                "AI_INTERPRETATION",
                "IA opcional",
                "intelligence",
                "OPTIONAL",
                ai_detail,
                required=False,
                metric=_int(results_summary.get("with_ai_analysis")),
            ),
        ]

        scenario_map = {row["code"]: row for row in journey}
        scenarios = [
            {
                "id": "company-switch",
                "label": "Cambiar empresa y confirmar aislamiento de contexto",
                "view": "companies",
                "status": "READY",
                "precondition": "Dos empresas solo si quieres comprobar el cambio; una empresa basta para el resto del UAT.",
                "expected": "La selección cambia de forma explícita y las superficies se recalculan para esa empresa.",
            },
            {
                "id": "inbox-to-crm",
                "label": "Inbox → Lead Intake → CRM",
                "view": "commercial-desk",
                "status": scenario_map["COMMERCIAL_FLOW"]["status"],
                "precondition": "Una interacción cached o un lead controlado con identidad exacta.",
                "expected": "No hay fuzzy matching ni conversión CRM automática; cada handoff exige acción del usuario.",
            },
            {
                "id": "pipeline-followup",
                "label": "Oportunidad → etapa → seguimiento",
                "view": "crm",
                "tab": "pipeline",
                "status": scenario_map["PIPELINE"]["status"],
                "precondition": "Una oportunidad abierta.",
                "expected": "Cambiar etapa exige Guardar; completar o reprogramar seguimiento reutiliza las rutas CRM certificadas.",
            },
            {
                "id": "campaign-execution",
                "label": "Campaña → creativo → calendario/pauta",
                "view": "execution",
                "status": scenario_map["EXECUTION_HANDOFF"]["status"],
                "precondition": "Una campaña activa; para cerrar el tramo prepara un creativo y una salida.",
                "expected": "El workspace navega a módulos canónicos; no publica ni activa anuncios por sí solo.",
            },
            {
                "id": "results-decision",
                "label": "Distribución → evidencia → decisión humana",
                "view": "intelligence",
                "status": scenario_map["RESULTS_LEARNING"]["status"],
                "precondition": "Distribución observada y snapshot explícito de resultados.",
                "expected": "Métricas, atribución LAST_CAPTURED_TOUCH y decisión humana permanecen separadas.",
            },
            {
                "id": "optional-ai",
                "label": "Decisión → interpretación IA opcional",
                "view": "intelligence",
                "status": "OPTIONAL",
                "precondition": "Provider/modelo configurado y evidencia suficiente.",
                "expected": "La IA requiere confirmación y nunca ejecuta publicación, pauta, CRM o decisión.",
            },
        ]

        workflows_dir = self.repo_root / ".github" / "workflows"
        workflow_names = sorted({
            path.name
            for pattern in ("*.yml", "*.yaml")
            for path in workflows_dir.glob(pattern)
        }) if workflows_dir.is_dir() else []
        canonical_workflows_only = set(workflow_names) == _CANONICAL_WORKFLOWS

        gaps = [
            {"code": row["code"], "label": row["label"], "status": row["status"], "view": row["view"]}
            for row in journey
            if row["required"] and row["status"] not in {"READY"}
        ]

        return {
            "schema": "binario.marketing.product-uat-readiness.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "company": {"id": company.id, "name": company.name},
            "summary": {
                "required_steps": sum(1 for row in journey if row["required"]),
                "ready_steps": sum(1 for row in journey if row["required"] and row["status"] == "READY"),
                "scenario_gaps": len(gaps),
                "ready_for_manual_uat": True,
                "production_ready": False,
                "physical_uat_recorded": False,
            },
            "journey": journey,
            "scenario_gaps": gaps,
            "manual_scenarios": scenarios,
            "continuity": {
                "primary_views": ["home", "commercial-desk", "crm", "campaigns", "execution", "intelligence"],
                "company_context_persistent": True,
                "cross_surface_navigation_explicit": True,
            },
            "contracts": {
                "workflow_count": len(workflow_names),
                "workflows": workflow_names,
                "canonical_workflows_only": canonical_workflows_only,
                "loopback_default": True,
                "cloud_required": False,
                "provider_polling": False,
                "automatic_marketing_execution": False,
            },
            "release_boundary": {
                "version": __version__,
                "release_ready": RELEASE_READY,
                "release_tag": RELEASE_TAG,
                "physical_uat_required": True,
                "physical_uat_recorded": False,
                "distribution_signing_certified": False,
                "notarization_certified": False,
                "production_ready": False,
            },
            "evidence": {
                "workdesk_next_action": workdesk.get("next_action"),
                "commercial_summary": commercial_summary,
                "pipeline_summary": pipeline_summary,
                "execution_summary": execution_summary,
                "results_summary": results_summary,
                "latest_snapshot": latest_snapshot,
                "human_decision_campaigns": decision_campaigns,
            },
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "ai_generation_performed": False,
                "automatic_message_send": False,
                "automatic_crm_conversion": False,
                "automatic_stage_change": False,
                "automatic_publish": False,
                "automatic_ad_activation": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 66 adds a GET-only UAT projection and UX hardening browser layer."""

    def _wave66_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/results-intelligence.js":
            target = self.server.runtime.repo_root / "web" / "results-intelligence.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave66AfterResultsIntelligence(){
  if(document.querySelector('script[data-uat-readiness-wave66]'))return;
  const uat=document.createElement('script');
  uat.src='/uat-readiness.js';
  uat.defer=true;
  uat.dataset.uatReadinessWave66='1';
  document.head.append(uat);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/uat-readiness.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "uat-readiness":
                self._json(self.server.runtime.product_uat_readiness(parts[2]))
                return
        except Exception as exc:
            self._wave66_error(exc)
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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
