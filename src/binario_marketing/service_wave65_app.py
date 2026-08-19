from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_wave64_app as base


_TERMINAL_CAMPAIGN_STATUSES = {"COMPLETED", "ARCHIVED"}


def _compact_ai_session(row) -> dict:
    output = row.output if isinstance(row.output, dict) else {}
    diagnosis = output.get("diagnosis") if isinstance(output.get("diagnosis"), list) else []
    recommendations = output.get("recommendations") if isinstance(output.get("recommendations"), list) else []
    compact_recommendations = []
    for item in recommendations[:5]:
        if not isinstance(item, dict):
            continue
        compact_recommendations.append({
            "title": str(item.get("title") or "").strip() or None,
            "why": str(item.get("why") or "").strip() or None,
            "priority": str(item.get("priority") or "").strip() or None,
            "area": str(item.get("area") or "").strip() or None,
            "next_step": str(item.get("next_step") or "").strip() or None,
        })
    return {
        "id": row.id,
        "provider": row.provider,
        "model": row.model,
        "created_at": row.created_at,
        "context_sha256": row.context_sha256,
        "summary": str(output.get("summary") or "").strip() or None,
        "diagnosis": [str(item).strip() for item in diagnosis[:5] if str(item).strip()],
        "recommendations": compact_recommendations,
        "recommendation_count": len(recommendations),
    }


class AppRuntime(base.AppRuntime):
    """Wave 65 composes execution, observed learning, attribution and optional AI history."""

    def results_intelligence_workspace(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        execution = self.campaign_execution_workspace(company.id)
        learning = self.learning_payload(company.id)
        attribution = self.attribution_payload(company.id)
        settings = self.ai_settings.get(company.id)

        learning_by_campaign = {row["id"]: row for row in learning.get("campaigns") or []}
        attribution_by_campaign = {row["id"]: row for row in attribution.get("campaigns") or []}
        latest_ai_by_campaign = {}
        for session in self.ai_sessions.list(company.id, limit=100):
            if session.task == "CAMPAIGN" and session.campaign_id and session.campaign_id not in latest_ai_by_campaign:
                latest_ai_by_campaign[session.campaign_id] = _compact_ai_session(session)

        latest_snapshot = learning.get("latest_snapshot")
        cards: list[dict] = []
        for execution_row in execution.get("campaigns") or []:
            campaign = execution_row["campaign"]
            campaign_id = campaign["id"]
            learned = learning_by_campaign.get(campaign_id) or {}
            attributed = attribution_by_campaign.get(campaign_id) or {}
            metrics = dict(learned.get("metrics") or {})
            decision = learned.get("latest_decision")
            latest_ai = latest_ai_by_campaign.get(campaign_id)

            observed = learned.get("evidence") == "OBSERVED"
            attributed_opportunities = int(attributed.get("attributed_opportunities") or 0)
            attributed_won = int(attributed.get("attributed_won") or 0)
            has_attribution = attributed_opportunities > 0
            has_signal = observed or has_attribution
            distribution_exists = bool(
                execution_row["organic"]["counts"].get("PUBLISHED", 0)
                or execution_row["paid"]["remote_paused"]
            )
            failed_publications = int(execution_row["organic"].get("failed") or 0)

            if attributed_won:
                evidence_level = "ATTRIBUTED_WON"
                evidence_label = "Venta atribuida"
            elif has_attribution:
                evidence_level = "ATTRIBUTED"
                evidence_label = "Oportunidad atribuida"
            elif observed:
                evidence_level = "OBSERVED"
                evidence_label = "Métricas observadas"
            else:
                evidence_level = "INSUFFICIENT"
                evidence_label = "Evidencia insuficiente"

            if failed_publications:
                priority = 0
                requires_attention = True
                next_action = {"code": "FIX_EXECUTION", "label": "Resolver publicación fallida", "view": "execution"}
            elif distribution_exists and latest_snapshot is None:
                priority = 1
                requires_attention = True
                next_action = {"code": "CAPTURE_RESULTS", "label": "Capturar resultados", "view": "analytics"}
            elif distribution_exists and not has_signal:
                priority = 2
                requires_attention = True
                next_action = {"code": "REVIEW_COVERAGE", "label": "Revisar cobertura de evidencia", "view": "analytics"}
            elif has_signal and not decision:
                priority = 3
                requires_attention = True
                next_action = {"code": "RECORD_DECISION", "label": "Registrar decisión humana", "view": "analytics"}
            elif has_signal and settings.provider and settings.model:
                priority = 4
                requires_attention = False
                next_action = {"code": "OPTIONAL_AI", "label": "Análisis IA opcional", "view": "intelligence"}
            elif has_signal:
                priority = 4
                requires_attention = False
                next_action = {"code": "REVIEW_RESULTS", "label": "Revisar resultados", "view": "analytics"}
            else:
                priority = 5
                requires_attention = False
                next_action = execution_row.get("next_action") or {"code": "EXECUTION", "label": "Continuar ejecución", "view": "execution"}

            summary_parts = []
            if observed:
                summary_parts.append(
                    f"{int(learned.get('organic_observations') or 0)} observaciones orgánicas · "
                    f"{int(learned.get('paid_observations') or 0)} de pauta"
                )
            if attributed_opportunities:
                summary_parts.append(
                    f"{attributed_opportunities} oportunidades atribuidas · {attributed_won} ganadas"
                )
            if not summary_parts:
                summary_parts.append("Aún no hay señal suficiente para interpretar desempeño")

            cards.append({
                "campaign": campaign,
                "execution": {
                    "requires_action": bool(execution_row.get("requires_action")),
                    "next_action": execution_row.get("next_action"),
                    "organic": execution_row.get("organic") or {},
                    "paid": execution_row.get("paid") or {},
                    "creative": execution_row.get("creative") or {},
                },
                "evidence": {
                    "level": evidence_level,
                    "label": evidence_label,
                    "has_signal": has_signal,
                    "observed": observed,
                    "organic_observations": int(learned.get("organic_observations") or 0),
                    "paid_observations": int(learned.get("paid_observations") or 0),
                    "metrics": metrics,
                    "summary": " · ".join(summary_parts),
                },
                "attribution": {
                    "attributed_contacts": int(attributed.get("attributed_contacts") or 0),
                    "attributed_opportunities": attributed_opportunities,
                    "attributed_won": attributed_won,
                    "value_by_currency": attributed.get("value_by_currency") or {},
                    "model": "LAST_CAPTURED_TOUCH",
                },
                "decision": decision,
                "latest_ai": latest_ai,
                "next_action": next_action,
                "priority": priority,
                "requires_attention": requires_attention,
            })

        cards.sort(key=lambda row: (
            row["priority"],
            row["campaign"].get("start_at") or "9999",
            row["campaign"]["name"].lower(),
            row["campaign"]["id"],
        ))
        active_cards = [row for row in cards if row["campaign"]["status"] not in _TERMINAL_CAMPAIGN_STATUSES]
        coverage = attribution.get("coverage") or {}
        return {
            "schema": "binario.marketing.results-intelligence.v1",
            "company": {"id": company.id, "name": company.name},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_snapshot": {
                "id": latest_snapshot.get("id"),
                "created_at": latest_snapshot.get("created_at"),
                "date_preset": latest_snapshot.get("date_preset"),
                "coverage": latest_snapshot.get("coverage") or {},
            } if latest_snapshot else None,
            "summary": {
                "campaigns": len(cards),
                "active_campaigns": len(active_cards),
                "requires_attention": sum(1 for row in active_cards if row["requires_attention"]),
                "with_observed_evidence": sum(1 for row in active_cards if row["evidence"]["observed"]),
                "with_attributed_opportunities": sum(1 for row in active_cards if row["attribution"]["attributed_opportunities"]),
                "with_human_decision": sum(1 for row in active_cards if row["decision"]),
                "with_ai_analysis": sum(1 for row in active_cards if row["latest_ai"]),
            },
            "attribution_coverage": {
                "opportunity_percent": coverage.get("opportunity_percent", 0.0),
                "attributed_opportunities": coverage.get("attributed_opportunities", 0),
                "crm_opportunities": coverage.get("crm_opportunities", 0),
                "model": "LAST_CAPTURED_TOUCH",
                "full_funnel_coverage_assumed": False,
            },
            "ai": {
                "configured": bool(settings.provider and settings.model),
                "provider": settings.provider,
                "model": settings.model,
                "generation_requires_explicit_user_action": True,
                "marketing_execution_authority": False,
            },
            "campaigns": cards,
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "ai_generation_performed": False,
                "decision_execution_performed": False,
                "automatic_recommendation_execution": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 65 adds a local GET projection and browser intelligence surface only."""

    def _wave65_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/execution-workspace.js":
            target = self.server.runtime.repo_root / "web" / "execution-workspace.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave65AfterExecutionWorkspace(){
  if(document.querySelector('script[data-results-intelligence-wave65]'))return;
  const intelligence=document.createElement('script');
  intelligence.src='/results-intelligence.js';
  intelligence.defer=true;
  intelligence.dataset.resultsIntelligenceWave65='1';
  document.head.append(intelligence);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/results-intelligence.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "results-intelligence":
                self._json(self.server.runtime.results_intelligence_workspace(parts[2]))
                return
        except Exception as exc:
            self._wave65_error(exc)
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
