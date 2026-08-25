from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_portfolio_control_tower_app as base


_OVERDUE_KINDS = {"publication_overdue", "crm_overdue"}
_TODAY_KINDS = {"publication_today", "crm_today"}
_UNSCHEDULED_KINDS = {"crm_unscheduled", "needs_opportunity", "needs_followup"}


def _parse_dt(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _lead_age_state(at: datetime | None, now: datetime) -> tuple[str, float | None]:
    if at is None:
        return "UNKNOWN_AGE", None
    hours = max(0.0, (now - at).total_seconds() / 3600.0)
    if hours <= 24:
        state = "RECEIVED_LE_24H"
    elif hours <= 72:
        state = "RECEIVED_24_72H"
    else:
        state = "RECEIVED_GT_72H"
    return state, round(hours, 2)


def normalize_action_timing(item: dict, *, now: datetime) -> dict:
    """Describe observed time semantics without inferring a deadline.

    Historical Action Center uses `due_at` for both operational due dates and the
    received timestamp of unresolved leads. This normalizer refuses to interpret
    that field without source/kind context.
    """
    source = str(item.get("source") or "").upper()
    kind = str(item.get("kind") or "").lower()
    raw_at = item.get("due_at")
    parsed = _parse_dt(raw_at)

    if source == "OPERATIONS" and kind in _OVERDUE_KINDS:
        return {
            "kind": "DEADLINE", "state": "OVERDUE", "at": raw_at,
            "is_deadline": True, "inferred": False,
            "explanation": "La mesa operativa ya clasificó este elemento como vencido; la fecha se conserva como deadline explícito.",
        }
    if source == "OPERATIONS" and kind in _TODAY_KINDS:
        return {
            "kind": "DEADLINE", "state": "TODAY", "at": raw_at,
            "is_deadline": True, "inferred": False,
            "explanation": "La mesa operativa ya clasificó este elemento para hoy; la fecha se conserva como deadline explícito.",
        }
    if source == "OPERATIONS" and kind == "publication_failed":
        return {
            "kind": "INCIDENT_AT", "state": "BLOCKED", "at": raw_at,
            "is_deadline": False, "inferred": False,
            "explanation": "La fecha describe el contexto temporal de una publicación fallida; no se reinterpreta como nuevo vencimiento.",
        }
    if source == "COMMERCIAL" and kind.startswith("lead_"):
        state, age_hours = _lead_age_state(parsed, now)
        return {
            "kind": "RECEIVED_AT", "state": state, "at": raw_at,
            "age_hours": age_hours, "is_deadline": False, "inferred": False,
            "explanation": "La marca temporal proviene de received_at del lead. Su antigüedad es observacional y nunca constituye deadline.",
        }
    if kind in _UNSCHEDULED_KINDS:
        return {
            "kind": "UNSCHEDULED", "state": "UNSCHEDULED", "at": None,
            "is_deadline": False, "inferred": False,
            "explanation": "La acción requiere agenda humana y no tiene un vencimiento explícito en la fuente canónica.",
        }
    if source == "OPERATIONS" and raw_at:
        return {
            "kind": "OPERATIONAL_AT", "state": "OBSERVED_AT", "at": raw_at,
            "is_deadline": False, "inferred": False,
            "explanation": "Existe una fecha operativa, pero el tipo de acción no autoriza llamarla deadline.",
        }
    return {
        "kind": "UNDATED_ACTION", "state": "UNDATED", "at": None,
        "is_deadline": False, "inferred": False,
        "explanation": "No existe una fecha con semántica suficiente para construir un deadline responsable.",
    }


def portfolio_cadence_projection(runtime, *, generated_at: str | None = None) -> dict:
    portfolio = runtime.portfolio_control_tower()
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    now = _parse_dt(generated) or datetime.now(timezone.utc)

    queue: list[dict] = []
    for source_item in portfolio.get("queue") or []:
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

    received_age = {"le_24h": 0, "h24_72": 0, "gt_72h": 0, "unknown": 0}
    for item in buckets["received_leads"]:
        state = item["timing"]["state"]
        if state == "RECEIVED_LE_24H":
            received_age["le_24h"] += 1
        elif state == "RECEIVED_24_72H":
            received_age["h24_72"] += 1
        elif state == "RECEIVED_GT_72H":
            received_age["gt_72h"] += 1
        else:
            received_age["unknown"] += 1

    first_deadline = next((item for item in queue if item["timing"]["is_deadline"]), None)
    return {
        "schema": "binario.marketing.portfolio-cadence.v1",
        "generated_at": generated,
        "portfolio_schema": portfolio.get("schema"),
        "summary": {
            "queue_total": len(queue),
            "blocked_incidents": len(buckets["blocked_incidents"]),
            "overdue_deadlines": len(buckets["overdue_deadlines"]),
            "today_deadlines": len(buckets["today_deadlines"]),
            "received_leads": len(buckets["received_leads"]),
            "unscheduled": len(buckets["unscheduled"]),
            "undated": len(buckets["undated"]),
            "received_age": received_age,
        },
        "next_action": queue[0] if queue else None,
        "next_explicit_deadline": first_deadline,
        "buckets": buckets,
        "queue": queue,
        "contracts": {
            "portfolio_order_preserved": True,
            "timing_never_reprioritizes": True,
            "due_at_requires_source_semantics": True,
            "received_at_never_deadline": True,
            "no_inferred_deadlines": True,
            "lead_age_is_observational_only": True,
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
    """Post-W99 chain with source-aware action timing semantics."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def portfolio_cadence(self) -> dict:
        return portfolio_cadence_projection(self)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path == "/portfolio-control-tower.js":
            target = self.server.runtime.repo_root / "web" / "portfolio-control-tower.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99PortfolioCadence(){
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
    print(f"BINARIO Marketing App · post-W99 portfolio cadence: {url}")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


__all__ = [
    "AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve",
    "normalize_action_timing", "portfolio_cadence_projection",
]
