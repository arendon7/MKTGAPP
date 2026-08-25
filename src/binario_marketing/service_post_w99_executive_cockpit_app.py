from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_decision_review_app as base


_STATE_ORDER = {"BLOCKED": 0, "ATTENTION": 1, "STABLE": 2}


def _count(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _lane(*, key: str, label: str, state: str, headline: str, detail: str,
          view: str, action_label: str, metrics: dict) -> dict:
    return {
        "key": key,
        "label": label,
        "state": state,
        "headline": headline,
        "detail": detail,
        "action": {"view": view, "label": action_label},
        "metrics": metrics,
    }


def _state_from_counts(*, blocking: int = 0, critical: int = 0, attention: int = 0) -> str:
    if blocking or critical:
        return "BLOCKED"
    if attention:
        return "ATTENTION"
    return "STABLE"


def _source_attention(queue: list[dict], source: str) -> dict:
    rows = [row for row in queue if str(row.get("source") or "").upper() == source]
    return {
        "total": len(rows),
        "blocking": sum(1 for row in rows if row.get("blocking")),
        "critical": sum(1 for row in rows if str(row.get("urgency") or "").upper() == "CRITICAL"),
        "high": sum(1 for row in rows if str(row.get("urgency") or "").upper() == "HIGH"),
        "medium": sum(1 for row in rows if str(row.get("urgency") or "").upper() == "MEDIUM"),
        "low": sum(1 for row in rows if str(row.get("urgency") or "").upper() == "LOW"),
    }


def compose_executive_cockpit(*, company: dict, action_center: dict, pipeline: dict,
                              outcomes: dict, results: dict, review: dict,
                              generated_at: str | None = None) -> dict:
    """Compose a read-only executive surface from existing authoritative projections.

    It classifies deterministic operational states only. It does not calculate a
    business-health score, probability of close, causal lift or blended-currency value.
    """
    action_summary = action_center.get("summary") or {}
    action_queue = list(action_center.get("queue") or [])
    pipeline_summary = pipeline.get("summary") or {}
    outcome_summary = outcomes.get("summary") or {}
    results_summary = results.get("summary") or {}
    review_summary = review.get("summary") or {}

    operations_source = _source_attention(action_queue, "OPERATIONS")
    commercial_source = _source_attention(action_queue, "COMMERCIAL")
    campaign_source = _source_attention(action_queue, "CAMPAIGN")

    operations_state = _state_from_counts(
        blocking=operations_source["blocking"],
        critical=operations_source["critical"],
        attention=operations_source["high"],
    )
    commercial_attention = _count(pipeline_summary.get("requires_attention")) + _count(
        outcome_summary.get("attention")
    )
    commercial_state = _state_from_counts(
        blocking=commercial_source["blocking"],
        critical=commercial_source["critical"],
        attention=commercial_source["high"] + commercial_attention,
    )
    campaign_attention = _count(results_summary.get("requires_attention"))
    campaign_state = _state_from_counts(
        blocking=campaign_source["blocking"],
        critical=campaign_source["critical"],
        attention=campaign_source["high"] + campaign_attention,
    )
    decision_attention = _count(review_summary.get("ready_for_review")) + _count(
        review_summary.get("follow_through_required")
    )
    decision_state = _state_from_counts(attention=decision_attention)

    lanes = [
        _lane(
            key="OPERATIONS", label="Operación", state=operations_state,
            headline=("Hay bloqueos operativos" if operations_state == "BLOCKED" else
                      "Hay prioridades operativas" if operations_state == "ATTENTION" else
                      "Operación sin bloqueos detectados"),
            detail=(f"{operations_source['critical']} críticas · "
                    f"{operations_source['high']} altas · "
                    f"{operations_source['blocking']} bloqueantes"),
            view="action-center", action_label="Abrir prioridades",
            metrics={
                "queue_total": operations_source["total"],
                "critical": operations_source["critical"],
                "high": operations_source["high"],
                "blocking": operations_source["blocking"],
            },
        ),
        _lane(
            key="COMMERCIAL", label="Comercial", state=commercial_state,
            headline=("Hay bloqueos comerciales" if commercial_state == "BLOCKED" else
                      "El pipeline requiere atención" if commercial_state == "ATTENTION" else
                      "Pipeline sin alertas determinísticas"),
            detail=(f"{_count(pipeline_summary.get('open_opportunities'))} abiertas · "
                    f"{_count(pipeline_summary.get('requires_attention'))} requieren atención · "
                    f"{_count(outcome_summary.get('attributed_won'))} ganadas atribuidas"),
            view="crm", action_label="Abrir pipeline",
            metrics={
                "open_opportunities": _count(pipeline_summary.get("open_opportunities")),
                "requires_attention": _count(pipeline_summary.get("requires_attention")),
                "captured_leads": _count(outcome_summary.get("captured_leads")),
                "attributed_opportunities": _count(outcome_summary.get("attributed_opportunities")),
                "attributed_won": _count(outcome_summary.get("attributed_won")),
                "critical_actions": commercial_source["critical"],
                "blocking_actions": commercial_source["blocking"],
            },
        ),
        _lane(
            key="CAMPAIGNS", label="Campañas", state=campaign_state,
            headline=("Hay bloqueos de campaña" if campaign_state == "BLOCKED" else
                      "Hay campañas que requieren intervención" if campaign_state == "ATTENTION" else
                      "Campañas sin alertas de resultados"),
            detail=(f"{_count(results_summary.get('active_campaigns'))} activas · "
                    f"{_count(results_summary.get('requires_attention'))} requieren atención · "
                    f"{_count(results_summary.get('with_observed_evidence'))} con evidencia observada"),
            view="analytics", action_label="Abrir resultados",
            metrics={
                "active_campaigns": _count(results_summary.get("active_campaigns")),
                "requires_attention": _count(results_summary.get("requires_attention")),
                "with_observed_evidence": _count(results_summary.get("with_observed_evidence")),
                "with_attributed_opportunities": _count(results_summary.get("with_attributed_opportunities")),
                "with_human_decision": _count(results_summary.get("with_human_decision")),
                "critical_actions": campaign_source["critical"],
                "blocking_actions": campaign_source["blocking"],
            },
        ),
        _lane(
            key="DECISIONS", label="Decisiones", state=decision_state,
            headline=("Hay decisiones por revisar o ejecutar" if decision_state == "ATTENTION" else
                      "Sin revisiones de decisión pendientes"),
            detail=(f"{_count(review_summary.get('ready_for_review'))} listas para revisión · "
                    f"{_count(review_summary.get('follow_through_required'))} requieren seguimiento · "
                    f"{_count(review_summary.get('awaiting_evidence'))} esperando evidencia"),
            view="decision-review", action_label="Revisar decisiones",
            metrics={
                "ready_for_review": _count(review_summary.get("ready_for_review")),
                "follow_through_required": _count(review_summary.get("follow_through_required")),
                "awaiting_evidence": _count(review_summary.get("awaiting_evidence")),
            },
        ),
    ]
    lanes.sort(key=lambda row: (_STATE_ORDER.get(row["state"], 9), row["key"]))

    overall_state = min(
        (row["state"] for row in lanes),
        key=lambda state: _STATE_ORDER.get(state, 9),
        default="STABLE",
    )
    if overall_state == "BLOCKED":
        headline = "Hay bloqueos que deben resolverse antes de optimizar"
    elif overall_state == "ATTENTION":
        headline = "La operación está activa y existen frentes que requieren decisión"
    else:
        headline = "No se detectan bloqueos ni alertas determinísticas"

    top_actions = action_queue[:8]
    executive_points: list[dict] = []
    if action_center.get("next_action"):
        executive_points.append({
            "code": "NEXT_ACTION",
            "label": "Prioridad inmediata",
            "text": action_center["next_action"].get("title"),
            "detail": action_center["next_action"].get("detail"),
            "view": (action_center["next_action"].get("action") or {}).get("view"),
        })
    if commercial_attention or commercial_source["critical"] or commercial_source["high"]:
        executive_points.append({
            "code": "COMMERCIAL_ATTENTION",
            "label": "Atención comercial",
            "text": f"{_count(pipeline_summary.get('requires_attention'))} oportunidad(es) requieren seguimiento determinístico.",
            "detail": "No es forecast ni probabilidad de cierre; proviene de fechas, actividades o ausencia de siguiente acción.",
            "view": "crm",
        })
    if decision_attention:
        executive_points.append({
            "code": "DECISION_ATTENTION",
            "label": "Gobierno de decisiones",
            "text": f"{decision_attention} decisión(es) requieren revisión o seguimiento humano.",
            "detail": "La evidencia posterior habilita revisión, pero no prueba causalidad ni ejecuta la decisión.",
            "view": "decision-review",
        })
    if campaign_attention or campaign_source["critical"] or campaign_source["high"]:
        executive_points.append({
            "code": "CAMPAIGN_ATTENTION",
            "label": "Campañas",
            "text": f"{campaign_attention} campaña(s) requieren una acción explícita en Results Intelligence.",
            "detail": "Se conserva la recomendación del módulo canónico sin crear una segunda prioridad.",
            "view": "analytics",
        })
    executive_points = executive_points[:4]

    latest_snapshot = results.get("latest_snapshot")
    projected_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema": "binario.marketing.executive-cockpit.v1",
        "company": {"id": company.get("id"), "name": company.get("name")},
        "generated_at": projected_at,
        "status": {
            "state": overall_state,
            "headline": headline,
            "blocking": _count(action_summary.get("blocking")),
            "requires_attention": sum(1 for row in lanes if row["state"] == "ATTENTION"),
            "stable_lanes": sum(1 for row in lanes if row["state"] == "STABLE"),
        },
        "executive_brief": executive_points,
        "next_action": action_center.get("next_action"),
        "top_actions": top_actions,
        "lanes": lanes,
        "commercial": {
            "pipeline": {
                "opportunities": _count(pipeline_summary.get("opportunities")),
                "open_opportunities": _count(pipeline_summary.get("open_opportunities")),
                "requires_attention": _count(pipeline_summary.get("requires_attention")),
                "proposals": _count(pipeline_summary.get("proposals")),
                "won": _count(pipeline_summary.get("won")),
                "lost": _count(pipeline_summary.get("lost")),
                "open_amounts_by_currency": pipeline_summary.get("amounts_by_currency") or [],
            },
            "attribution": {
                "captured_leads": _count(outcome_summary.get("captured_leads")),
                "converted_leads": _count(outcome_summary.get("converted_leads")),
                "attributed_opportunities": _count(outcome_summary.get("attributed_opportunities")),
                "attributed_won": _count(outcome_summary.get("attributed_won")),
                "value_by_currency": outcome_summary.get("value_by_currency") or {},
                "credit_model": "LAST_CAPTURED_TOUCH",
            },
        },
        "campaigns": {
            "active": _count(results_summary.get("active_campaigns")),
            "requires_attention": _count(results_summary.get("requires_attention")),
            "with_observed_evidence": _count(results_summary.get("with_observed_evidence")),
            "with_attributed_opportunities": _count(results_summary.get("with_attributed_opportunities")),
            "with_human_decision": _count(results_summary.get("with_human_decision")),
            "decision_review": review_summary,
        },
        "evidence": {
            "latest_snapshot": latest_snapshot,
            "local_projection_generated_at": projected_at,
            "provider_refresh_performed": False,
            "provider_freshness_assumed": False,
        },
        "contracts": {
            "single_executive_read_model": True,
            "canonical_modules_remain_authoritative": True,
            "action_center_order_preserved": True,
            "lane_state_uses_authoritative_source": True,
            "no_business_health_score": True,
            "no_probability_of_close": True,
            "no_causal_inference": True,
            "no_mixed_currency_aggregation": True,
            "human_execution_required": True,
        },
        "safety": {
            "company_scoped": True,
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "business_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
        },
    }


class AppRuntime(base.AppRuntime):
    """Post-W99 chain with one executive read model over canonical product surfaces."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def executive_cockpit(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return compose_executive_cockpit(
            company={"id": company.id, "name": company.name},
            action_center=self.action_center(company.id),
            pipeline=self.commercial_pipeline(company.id),
            outcomes=self.commercial_outcomes(company.id),
            results=self.results_intelligence_workspace(company.id),
            review=self.decision_review(company.id),
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path == "/decision-review.js":
            target = self.server.runtime.repo_root / "web" / "decision-review.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99ExecutiveCockpit(){
  if(document.querySelector('script[data-post-w99-executive-cockpit]'))return;
  const script=document.createElement('script');
  script.src='/executive-cockpit.js';
  script.defer=true;
  script.dataset.postW99ExecutiveCockpit='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/executive-cockpit.js":
            target = self.server.runtime.repo_root / "web" / "executive-cockpit.js"
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
        if parsed.path == "/executive-cockpit.js":
            self._static(parsed.path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "executive-cockpit":
                self._json(self.server.runtime.executive_cockpit(parts[2]))
                return
        except KeyError as exc:
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
            return
        except (ValueError, TypeError) as exc:
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except Exception as exc:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")
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
    print(f"BINARIO Marketing App · post-W99 executive cockpit: {url}")
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


__all__ = [
    "AppRuntime",
    "MarketingHandler",
    "MarketingHTTPServer",
    "compose_executive_cockpit",
    "create_server",
    "serve",
]
