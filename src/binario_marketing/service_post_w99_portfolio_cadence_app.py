from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_evidence_observability_integrated_app as base


_OVERDUE_KINDS = {"publication_overdue", "crm_overdue"}
_TODAY_KINDS = {"publication_today", "crm_today"}
_UNSCHEDULED_KINDS = {"crm_unscheduled", "needs_opportunity", "needs_followup"}


def _parse_dt(value: object) -> tuple[datetime | None, str]:
    text = str(value or "").strip()
    if not text:
        return None, "MISSING"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None, "INVALID"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc), "VALID"


def _timestamp_status(value: object, *, now: datetime, expected: bool) -> dict:
    parsed, quality = _parse_dt(value)
    if quality == "MISSING":
        return {
            "parsed": None,
            "quality": "MISSING_EXPECTED_TIMESTAMP" if expected else "NOT_APPLICABLE",
            "temporal_anomaly": bool(expected),
        }
    if quality == "INVALID":
        return {"parsed": None, "quality": "INVALID_TIMESTAMP", "temporal_anomaly": True}
    assert parsed is not None
    if parsed > now:
        return {"parsed": parsed, "quality": "FUTURE_TIMESTAMP", "temporal_anomaly": True}
    return {"parsed": parsed, "quality": "VALID_PAST_OR_PRESENT", "temporal_anomaly": False}


def _lead_age_state(value: object, *, now: datetime) -> tuple[str, float | None, dict]:
    audit = _timestamp_status(value, now=now, expected=True)
    parsed = audit["parsed"]
    if audit["quality"] == "MISSING_EXPECTED_TIMESTAMP":
        return "MISSING_RECEIVED_AT", None, audit
    if audit["quality"] == "INVALID_TIMESTAMP":
        return "INVALID_RECEIVED_AT", None, audit
    if audit["quality"] == "FUTURE_TIMESTAMP":
        return "FUTURE_RECEIVED_AT", None, audit
    assert parsed is not None
    age_hours = (now - parsed).total_seconds() / 3600.0
    if age_hours <= 24:
        state = "RECEIVED_LE_24H"
    elif age_hours <= 72:
        state = "RECEIVED_24_72H"
    else:
        state = "RECEIVED_GT_72H"
    return state, round(age_hours, 2), audit


def _timing(
    *,
    kind: str,
    state: str,
    at: object,
    is_deadline: bool,
    explanation: str,
    timestamp_quality: str,
    temporal_anomaly: bool,
    age_hours: float | None = None,
) -> dict:
    return {
        "kind": kind,
        "state": state,
        "at": at,
        "age_hours": age_hours,
        "is_deadline": bool(is_deadline),
        "inferred": False,
        "timestamp_quality": timestamp_quality,
        "temporal_anomaly": bool(temporal_anomaly),
        "explanation": explanation,
    }


def normalize_action_timing(item: dict, *, now: datetime) -> dict:
    """Attach source-aware temporal meaning without creating deadlines or priority."""
    source = str(item.get("source") or "").upper()
    kind = str(item.get("kind") or "").lower()
    raw_at = item.get("due_at")

    if source == "OPERATIONS" and kind in _OVERDUE_KINDS:
        audit = _timestamp_status(raw_at, now=now, expected=True)
        return _timing(
            kind="DEADLINE",
            state="OVERDUE",
            at=raw_at,
            is_deadline=True,
            timestamp_quality=audit["quality"],
            temporal_anomaly=audit["temporal_anomaly"],
            explanation=(
                "La fuente operativa ya clasificó este elemento como vencido. "
                "Portfolio Cadence conserva esa clasificación y audita la fecha sin recalcular prioridad."
            ),
        )

    if source == "OPERATIONS" and kind in _TODAY_KINDS:
        audit = _timestamp_status(raw_at, now=now, expected=True)
        return _timing(
            kind="DEADLINE",
            state="TODAY",
            at=raw_at,
            is_deadline=True,
            timestamp_quality=audit["quality"],
            temporal_anomaly=audit["temporal_anomaly"],
            explanation=(
                "La fuente operativa ya clasificó este elemento para hoy. "
                "La fecha se conserva como deadline explícito de la fuente, sin inferir uno nuevo."
            ),
        )

    if source == "OPERATIONS" and kind == "publication_failed":
        audit = _timestamp_status(raw_at, now=now, expected=False)
        return _timing(
            kind="INCIDENT_AT",
            state="BLOCKED",
            at=raw_at,
            is_deadline=False,
            timestamp_quality=audit["quality"],
            temporal_anomaly=audit["temporal_anomaly"],
            explanation=(
                "La marca temporal describe el contexto de una publicación fallida; "
                "nunca se convierte en un nuevo vencimiento."
            ),
        )

    if source == "COMMERCIAL" and kind.startswith("lead_"):
        state, age_hours, audit = _lead_age_state(raw_at, now=now)
        return _timing(
            kind="RECEIVED_AT",
            state=state,
            at=raw_at,
            age_hours=age_hours,
            is_deadline=False,
            timestamp_quality=audit["quality"],
            temporal_anomaly=audit["temporal_anomaly"],
            explanation=(
                "La marca temporal proviene de received_at del lead. "
                "Su antigüedad es observacional y nunca constituye deadline."
            ),
        )

    if kind in _UNSCHEDULED_KINDS:
        return _timing(
            kind="UNSCHEDULED",
            state="UNSCHEDULED",
            at=None,
            is_deadline=False,
            timestamp_quality="NOT_APPLICABLE",
            temporal_anomaly=False,
            explanation=(
                "La acción requiere agenda humana y no tiene un vencimiento explícito "
                "en la fuente canónica."
            ),
        )

    if source == "OPERATIONS" and raw_at:
        audit = _timestamp_status(raw_at, now=now, expected=False)
        return _timing(
            kind="OPERATIONAL_AT",
            state="OBSERVED_AT",
            at=raw_at,
            is_deadline=False,
            timestamp_quality=audit["quality"],
            temporal_anomaly=audit["temporal_anomaly"],
            explanation=(
                "Existe una marca temporal operativa, pero el tipo de acción no autoriza "
                "llamarla deadline."
            ),
        )

    return _timing(
        kind="UNDATED_ACTION",
        state="UNDATED",
        at=None,
        is_deadline=False,
        timestamp_quality="NOT_APPLICABLE",
        temporal_anomaly=False,
        explanation=(
            "No existe una fecha con semántica suficiente para construir un deadline responsable."
        ),
    )


def _generated_now(generated_at: str | None) -> tuple[str, datetime]:
    if generated_at is None:
        now = datetime.now(timezone.utc)
        return now.isoformat(), now
    parsed, quality = _parse_dt(generated_at)
    if quality != "VALID" or parsed is None:
        raise ValueError("generated_at must be a valid ISO-8601 timestamp")
    return generated_at, parsed


def portfolio_cadence_projection(runtime, *, generated_at: str | None = None) -> dict:
    """Project source-aware timing over the canonical portfolio queue.

    Portfolio Control Tower remains the only priority authority. This projection never
    resorts the queue and explicitly declares when the parent portfolio queue is capped.
    """
    portfolio = runtime.portfolio_control_tower()
    generated, now = _generated_now(generated_at)
    source_queue = list(portfolio.get("queue") or [])
    queue: list[dict] = []
    for source_item in source_queue:
        item = deepcopy(source_item)
        item["timing"] = normalize_action_timing(item, now=now)
        queue.append(item)

    buckets = {
        "blocked_incidents": [],
        "overdue_deadlines": [],
        "today_deadlines": [],
        "received_leads": [],
        "unscheduled": [],
        "undated": [],
        "other_observed": [],
    }
    for item in queue:
        timing = item["timing"]
        if timing["kind"] == "INCIDENT_AT":
            buckets["blocked_incidents"].append(item)
        elif timing["kind"] == "DEADLINE" and timing["state"] == "OVERDUE":
            buckets["overdue_deadlines"].append(item)
        elif timing["kind"] == "DEADLINE" and timing["state"] == "TODAY":
            buckets["today_deadlines"].append(item)
        elif timing["kind"] == "RECEIVED_AT":
            buckets["received_leads"].append(item)
        elif timing["kind"] == "UNSCHEDULED":
            buckets["unscheduled"].append(item)
        elif timing["kind"] == "UNDATED_ACTION":
            buckets["undated"].append(item)
        else:
            buckets["other_observed"].append(item)

    received_age = {
        "le_24h": 0,
        "h24_72": 0,
        "gt_72h": 0,
        "future": 0,
        "invalid": 0,
        "missing": 0,
    }
    received_state_to_key = {
        "RECEIVED_LE_24H": "le_24h",
        "RECEIVED_24_72H": "h24_72",
        "RECEIVED_GT_72H": "gt_72h",
        "FUTURE_RECEIVED_AT": "future",
        "INVALID_RECEIVED_AT": "invalid",
        "MISSING_RECEIVED_AT": "missing",
    }
    for item in buckets["received_leads"]:
        key = received_state_to_key.get(item["timing"]["state"])
        if key:
            received_age[key] += 1

    anomalies = [
        {
            "portfolio_id": item.get("portfolio_id"),
            "id": item.get("id"),
            "company": deepcopy(item.get("company") or {}),
            "source": item.get("source"),
            "kind": item.get("kind"),
            "title": item.get("title"),
            "timing": deepcopy(item.get("timing") or {}),
        }
        for item in queue
        if bool((item.get("timing") or {}).get("temporal_anomaly"))
    ]

    first_deadline = next((item for item in queue if item["timing"]["is_deadline"]), None)
    portfolio_summary = portfolio.get("summary") or {}
    portfolio_queue_total = int(portfolio_summary.get("queue_total") or len(source_queue))
    displayed_queue_total = len(source_queue)
    parent_queue_truncated = portfolio_queue_total > displayed_queue_total

    return {
        "schema": "binario.marketing.portfolio-cadence.v2",
        "generated_at": generated,
        "portfolio_schema": portfolio.get("schema"),
        "summary": {
            "portfolio_queue_total": portfolio_queue_total,
            "displayed_queue_total": displayed_queue_total,
            "parent_queue_truncated": parent_queue_truncated,
            "blocked_incidents": len(buckets["blocked_incidents"]),
            "overdue_deadlines": len(buckets["overdue_deadlines"]),
            "today_deadlines": len(buckets["today_deadlines"]),
            "received_leads": len(buckets["received_leads"]),
            "unscheduled": len(buckets["unscheduled"]),
            "undated": len(buckets["undated"]),
            "other_observed": len(buckets["other_observed"]),
            "temporal_anomalies": len(anomalies),
            "received_age": received_age,
        },
        "next_action": queue[0] if queue else None,
        "first_explicit_deadline_in_priority_order": first_deadline,
        "buckets": buckets,
        "temporal_anomalies": anomalies,
        "queue": queue,
        "scope": {
            "parent": "PORTFOLIO_CONTROL_TOWER",
            "parent_queue_total": portfolio_queue_total,
            "projected_queue_total": displayed_queue_total,
            "parent_queue_truncated": parent_queue_truncated,
            "completeness": "PARTIAL_PARENT_QUEUE" if parent_queue_truncated else "FULL_PARENT_QUEUE",
        },
        "contracts": {
            "portfolio_control_tower_is_priority_authority": True,
            "exact_parent_queue_order_preserved": True,
            "timing_never_reprioritizes": True,
            "due_at_requires_source_semantics": True,
            "received_at_never_deadline": True,
            "future_received_at_never_zero_age": True,
            "invalid_timestamp_never_coerced": True,
            "no_inferred_deadlines": True,
            "lead_age_is_observational_only": True,
            "deadline_selection_rule": "FIRST_DEADLINE_IN_CANONICAL_PRIORITY_ORDER",
            "parent_queue_scope_declared": True,
            "human_scheduling_required": True,
        },
        "safety": {
            "local_state_only": True,
            "read_only_projection": True,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "business_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
            "forecasting": False,
            "causal_inference": False,
        },
    }


class AppRuntime(base.AppRuntime):
    """Post-W99 terminal with source-aware portfolio timing semantics."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def portfolio_cadence(self) -> dict:
        return portfolio_cadence_projection(self)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Append Portfolio Cadence after Evidence Observability without replacing prior UI."""

    def _static(self, path: str) -> None:
        if path == "/evidence-observability.js":
            target = self.server.runtime.repo_root / "web" / "evidence-observability.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PortfolioCadenceAfterEvidenceObservability(){
  if(document.querySelector('script[data-post-w99-portfolio-cadence]'))return;
  const script=document.createElement('script');
  script.src='/portfolio-cadence.js';
  script.defer=true;
  script.dataset.postW99PortfolioCadence='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/portfolio-cadence.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-cadence.js"
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
        if parsed.path == "/portfolio-cadence.js":
            self._static(parsed.path)
            return
        try:
            if parsed.path == "/api/portfolio-cadence":
                self._json(self.server.runtime.portfolio_cadence())
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
    print(f"BINARIO Marketing App · post-W99 Portfolio Cadence v2: {url}")
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
    "create_server",
    "normalize_action_timing",
    "portfolio_cadence_projection",
    "serve",
]
