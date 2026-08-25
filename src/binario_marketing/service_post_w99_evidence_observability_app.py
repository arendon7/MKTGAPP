from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_today_execution_app as base


_EVIDENCE_STATES = ("OBSERVED", "PARTIAL", "NOT_OBSERVED", "UNKNOWN")


def _text(value: object, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _parse_timestamp(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _freshness(observed_at: object, *, projected_at: str) -> dict:
    observed_text = _text(observed_at) or None
    projected = _parse_timestamp(projected_at)
    observed = _parse_timestamp(observed_text)
    if observed_text is None:
        classification = "NO_OBSERVATION_TIMESTAMP"
        age_seconds = None
    elif observed is None or projected is None:
        classification = "INVALID_TIMESTAMP"
        age_seconds = None
    elif observed > projected:
        classification = "FUTURE_OBSERVATION"
        age_seconds = None
    else:
        classification = "AGE_OBSERVED"
        age_seconds = int((projected - observed).total_seconds())
    return {
        "observed_at": observed_text,
        "as_of": projected_at,
        "age_seconds": age_seconds,
        "classification": classification,
        "fresh": None,
        "stale": None,
        "policy": "NO_STALENESS_THRESHOLD_CONFIGURED",
    }


def _latest_timestamp(values: list[object]) -> str | None:
    candidates: list[tuple[datetime, str]] = []
    for value in values:
        text = _text(value)
        parsed = _parse_timestamp(text)
        if parsed is not None:
            candidates.append((parsed, text))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _domain(
    *, key: str, label: str, status: str, headline: str, detail: str,
    observed_at: object, projected_at: str, coverage: dict, action: dict,
    caveats: list[str] | None = None,
) -> dict:
    if status not in _EVIDENCE_STATES:
        raise ValueError(f"unsupported evidence status: {status}")
    return {
        "key": key,
        "label": label,
        "status": status,
        "headline": headline,
        "detail": detail,
        "coverage": coverage,
        "freshness": _freshness(observed_at, projected_at=projected_at),
        "action": action,
        "caveats": list(caveats or []),
    }


def _results_snapshot_domain(results: dict, *, projected_at: str) -> dict:
    snapshot = results.get("latest_snapshot")
    summary = results.get("summary") or {}
    campaigns = int(summary.get("campaigns") or 0)
    if snapshot:
        created_at = snapshot.get("created_at")
        timestamp_ok = _parse_timestamp(created_at) is not None
        status = "OBSERVED" if timestamp_ok else "PARTIAL"
        headline = "Existe un snapshot local de resultados"
        detail = (
            "El snapshot conserva evidencia ya capturada. Esta vista no consulta al proveedor para actualizarla."
            if timestamp_ok else
            "Existe el snapshot, pero su timestamp no permite calcular antigüedad de forma confiable."
        )
    elif campaigns:
        created_at = None
        status = "NOT_OBSERVED"
        headline = "No hay snapshot de resultados capturado"
        detail = "Hay campañas en la proyección, pero no existe todavía un snapshot local de resultados."
    else:
        created_at = None
        status = "UNKNOWN"
        headline = "No hay población de campañas para evaluar snapshot"
        detail = "La ausencia de snapshot no se interpreta como desempeño ni como cero resultados."
    return _domain(
        key="RESULTS_SNAPSHOT",
        label="Snapshot de resultados",
        status=status,
        headline=headline,
        detail=detail,
        observed_at=created_at,
        projected_at=projected_at,
        coverage={
            "campaigns": campaigns,
            "snapshot_present": bool(snapshot),
            "date_preset": (snapshot or {}).get("date_preset"),
            "snapshot_coverage": (snapshot or {}).get("coverage") or {},
        },
        action={"label": "Abrir resultados", "view": "analytics"},
        caveats=["Un snapshot local no demuestra que el estado actual del proveedor sea el mismo."],
    )


def _campaign_evidence_domain(results: dict, *, projected_at: str) -> dict:
    rows = list(results.get("campaigns") or [])
    observed_rows = [row for row in rows if bool((row.get("evidence") or {}).get("has_signal"))]
    explicitly_observed = [row for row in rows if bool((row.get("evidence") or {}).get("observed"))]
    if not rows:
        status = "UNKNOWN"
        headline = "No hay campañas en la superficie de resultados"
    elif len(observed_rows) == len(rows):
        status = "OBSERVED"
        headline = "Todas las campañas proyectadas tienen alguna señal local"
    elif observed_rows:
        status = "PARTIAL"
        headline = "La cobertura de evidencia de campañas es parcial"
    else:
        status = "NOT_OBSERVED"
        headline = "No hay señal local suficiente en las campañas proyectadas"
    snapshot = results.get("latest_snapshot") or {}
    return _domain(
        key="CAMPAIGN_EVIDENCE",
        label="Evidencia por campaña",
        status=status,
        headline=headline,
        detail=(
            f"{len(observed_rows)} de {len(rows)} campaña(s) tienen señal local; "
            f"{len(explicitly_observed)} incluyen métricas observadas."
        ),
        observed_at=snapshot.get("created_at") if observed_rows else None,
        projected_at=projected_at,
        coverage={
            "campaigns": len(rows),
            "with_signal": len(observed_rows),
            "with_observed_marketing": len(explicitly_observed),
            "with_attributed_opportunities": sum(
                1 for row in rows if int((row.get("attribution") or {}).get("attributed_opportunities") or 0) > 0
            ),
        },
        action={"label": "Revisar cobertura", "view": "analytics"},
        caveats=[
            "Sin señal local no significa cero impresiones, cero clics, cero conversiones ni mal desempeño.",
            "La fecha del snapshot es global; no se inventa una fecha de observación por campaña.",
        ],
    )


def _commercial_attribution_domain(outcomes: dict, *, projected_at: str) -> dict:
    summary = outcomes.get("summary") or {}
    rows = list(outcomes.get("campaigns") or [])
    links = int(summary.get("tracking_links") or 0)
    captured_leads = int(summary.get("captured_leads") or 0)
    touches = int(summary.get("captured_touches") or 0)
    opportunities = int(summary.get("attributed_opportunities") or 0)
    won = int(summary.get("attributed_won") or 0)
    has_observed = any((captured_leads, touches, opportunities, won))
    if has_observed:
        status = "OBSERVED"
        headline = "Existe evidencia first-party o CRM atribuida"
    elif links:
        status = "PARTIAL"
        headline = "Existe instrumentación, pero no captura first-party observada"
    elif rows:
        status = "NOT_OBSERVED"
        headline = "No hay evidencia comercial atribuida en la proyección local"
    else:
        status = "UNKNOWN"
        headline = "No hay campañas comerciales para evaluar atribución"

    journey_times: list[object] = []
    for row in rows:
        for journey in row.get("journeys") or []:
            journey_times.append(journey.get("received_at"))
    observed_at = _latest_timestamp(journey_times)
    return _domain(
        key="COMMERCIAL_ATTRIBUTION",
        label="Atribución comercial",
        status=status,
        headline=headline,
        detail=(
            f"{links} link(s) instrumentado(s) · {captured_leads} lead(s) capturado(s) · "
            f"{opportunities} oportunidad(es) atribuidas · {won} ganada(s)."
        ),
        observed_at=observed_at,
        projected_at=projected_at,
        coverage={
            "campaigns": len(rows),
            "tracking_links": links,
            "captured_touches": touches,
            "captured_leads": captured_leads,
            "attributed_opportunities": opportunities,
            "attributed_won": won,
            "credit_model": "LAST_CAPTURED_TOUCH",
        },
        action={"label": "Abrir resultados comerciales", "view": "analytics"},
        caveats=[
            "Un tracking link es instrumentación, no prueba un clic.",
            "Ausencia de captura first-party no equivale a cero tráfico o cero interés.",
            "Los valores monetarios no se combinan entre monedas.",
        ],
    )


def _decision_evidence_domain(review: dict, *, projected_at: str) -> dict:
    rows = list(review.get("campaigns") or [])
    with_post_evidence = [row for row in rows if bool((row.get("post_decision_evidence") or {}).get("basis"))]
    if not rows:
        status = "UNKNOWN"
        headline = "No hay decisiones humanas de campaña para revisar"
    elif len(with_post_evidence) == len(rows):
        status = "OBSERVED"
        headline = "Todas las decisiones registradas tienen evidencia posterior"
    elif with_post_evidence:
        status = "PARTIAL"
        headline = "Solo parte de las decisiones tiene evidencia posterior"
    else:
        status = "NOT_OBSERVED"
        headline = "Aún no hay evidencia posterior a las decisiones registradas"

    timestamps: list[object] = []
    for row in rows:
        post = row.get("post_decision_evidence") or {}
        observed_marketing = post.get("observed_marketing") or {}
        timestamps.append(observed_marketing.get("created_at"))
        for crm_row in post.get("attributed_crm_updates") or []:
            timestamps.append(crm_row.get("event_at"))
        if post.get("campaign_terminal_after_decision"):
            timestamps.append((row.get("campaign") or {}).get("updated_at"))
    summary = review.get("summary") or {}
    return _domain(
        key="DECISION_EVIDENCE",
        label="Evidencia posterior a decisiones",
        status=status,
        headline=headline,
        detail=(
            f"{len(rows)} decisión(es) de campaña · {len(with_post_evidence)} con evidencia posterior · "
            f"{int(summary.get('awaiting_evidence') or 0)} esperando evidencia."
        ),
        observed_at=_latest_timestamp(timestamps),
        projected_at=projected_at,
        coverage={
            "campaigns_with_decision": len(rows),
            "with_post_decision_evidence": len(with_post_evidence),
            "ready_for_review": int(summary.get("ready_for_review") or 0),
            "follow_through_required": int(summary.get("follow_through_required") or 0),
            "awaiting_evidence": int(summary.get("awaiting_evidence") or 0),
        },
        action={"label": "Abrir revisión de decisiones", "view": "decision-review"},
        caveats=[
            "Evidencia posterior no demuestra que una decisión haya causado el resultado observado.",
            "Esta vista no califica una decisión como correcta o incorrecta.",
        ],
    )


def compose_evidence_observability(
    *, company: dict, results: dict, outcomes: dict, review: dict, projected_at: str | None = None
) -> dict:
    projected_at = projected_at or datetime.now(timezone.utc).isoformat()
    domains = [
        _results_snapshot_domain(results, projected_at=projected_at),
        _campaign_evidence_domain(results, projected_at=projected_at),
        _commercial_attribution_domain(outcomes, projected_at=projected_at),
        _decision_evidence_domain(review, projected_at=projected_at),
    ]
    counts = {state: 0 for state in _EVIDENCE_STATES}
    for row in domains:
        counts[row["status"]] += 1
    return {
        "schema": "binario.marketing.evidence-observability.v1",
        "projected_at": projected_at,
        "company": {"id": company.get("id"), "name": company.get("name")},
        "summary": {
            "domains": len(domains),
            "observed": counts["OBSERVED"],
            "partial": counts["PARTIAL"],
            "not_observed": counts["NOT_OBSERVED"],
            "unknown": counts["UNKNOWN"],
        },
        "domains": domains,
        "contracts": {
            "local_evidence_only": True,
            "absence_is_not_zero_performance": True,
            "no_staleness_threshold_configured": True,
            "age_is_measurement_not_freshness_judgment": True,
            "provider_refresh_required_for_current_provider_truth": True,
            "canonical_modules_remain_authoritative": True,
            "action_center_priority_unmodified": True,
            "today_selection_unmodified": True,
            "no_business_health_score": True,
            "no_causal_inference": True,
        },
        "safety": {
            "company_scoped": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "business_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
            "cloud_required": False,
        },
    }


class AppRuntime(base.AppRuntime):
    """Terminal post-W99 runtime adding local evidence observability."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def evidence_observability(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return compose_evidence_observability(
            company={"id": company.id, "name": company.name},
            results=self.results_intelligence_workspace(company.id),
            outcomes=self.commercial_outcomes(company.id),
            review=self.decision_review(company.id),
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose evidence observability as GET-only and chain it after Today."""

    def _static(self, path: str) -> None:
        if path == "/today-execution.js":
            target = self.server.runtime.repo_root / "web" / "today-execution.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99EvidenceObservabilityAfterToday(){
  if(document.querySelector('script[data-post-w99-evidence-observability]'))return;
  const script=document.createElement('script');
  script.src='/evidence-observability.js';
  script.defer=true;
  script.dataset.postW99EvidenceObservability='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/evidence-observability.js":
            target = self.server.runtime.repo_root / "web" / "evidence-observability.js"
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
        if parsed.path == "/evidence-observability.js":
            self._static(parsed.path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "evidence-observability":
                self._json(self.server.runtime.evidence_observability(parts[2]))
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
    print(f"BINARIO Marketing App · post-W99 Evidence Observability: {url}")
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
    "AppRuntime", "MarketingHandler", "MarketingHTTPServer",
    "compose_evidence_observability", "create_server", "serve",
]
