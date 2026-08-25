from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_integrated_cockpit_app as base


_FOCUS = {
    "CRITICAL": "NOW",
    "HIGH": "NOW",
    "MEDIUM": "TODAY",
    "LOW": "OPTIONAL",
}


def compose_today_execution(*, company: dict, action_center: dict, cockpit: dict,
                            generated_at: str | None = None, limit: int = 5) -> dict:
    """Project the canonical Action Center queue into one deliberately small workday list.

    Selection is intentionally boring: take the first ``limit`` items in the exact
    Action Center order. No score, value weighting, due-date reinterpretation or new
    business priority is introduced here.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5:
        raise ValueError("today execution limit must be an integer between 1 and 5")

    canonical_queue = list(action_center.get("queue") or [])
    selected: list[dict] = []
    for sequence, source_row in enumerate(canonical_queue[:limit], start=1):
        row = deepcopy(source_row)
        urgency = str(row.get("urgency") or "LOW").upper()
        row["operator"] = {
            "sequence": sequence,
            "focus": _FOCUS.get(urgency, "TODAY"),
            "is_primary": sequence == 1,
            "completion_owner": "CANONICAL_DESTINATION",
        }
        selected.append(row)

    now_count = sum(1 for row in selected if row["operator"]["focus"] == "NOW")
    today_count = sum(1 for row in selected if row["operator"]["focus"] == "TODAY")
    optional_count = sum(1 for row in selected if row["operator"]["focus"] == "OPTIONAL")
    blocking = sum(1 for row in selected if row.get("blocking"))
    critical = sum(1 for row in selected if str(row.get("urgency") or "").upper() == "CRITICAL")

    if blocking or critical:
        state = "BLOCKED"
        headline = "Resuelve primero el bloqueo que encabeza la cola"
    elif now_count:
        state = "ACTIVE"
        headline = "Hay trabajo de alta prioridad para ejecutar ahora"
    elif today_count:
        state = "ACTIVE"
        headline = "El plan de hoy está concentrado en trabajo de prioridad media"
    elif optional_count:
        state = "MAINTENANCE"
        headline = "No hay trabajo urgente; quedan tareas de mantenimiento"
    else:
        state = "CLEAR"
        headline = "No hay acciones pendientes en Action Center"

    source_counts: dict[str, int] = {}
    for row in selected:
        source = str(row.get("source") or "OTHER")
        source_counts[source] = source_counts.get(source, 0) + 1

    cockpit_status = cockpit.get("status") or {}
    cockpit_commercial = cockpit.get("commercial") or {}
    cockpit_campaigns = cockpit.get("campaigns") or {}
    return {
        "schema": "binario.marketing.today-execution.v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "company": {"id": company.get("id"), "name": company.get("name")},
        "status": {
            "state": state,
            "headline": headline,
            "primary_action_id": selected[0].get("id") if selected else None,
        },
        "summary": {
            "planned": len(selected),
            "now": now_count,
            "today": today_count,
            "optional": optional_count,
            "blocking": blocking,
            "remaining_queue": max(0, len(canonical_queue) - len(selected)),
            "canonical_queue_total": len(canonical_queue),
            "by_source": source_counts,
        },
        "primary_action": selected[0] if selected else None,
        "plan": selected,
        "overflow": {
            "count": max(0, len(canonical_queue) - len(selected)),
            "next_action_id": canonical_queue[len(selected)].get("id") if len(canonical_queue) > len(selected) else None,
            "owner_view": "action-center",
            "label": "Ver cola completa",
        },
        "executive_context": {
            "state": cockpit_status.get("state"),
            "headline": cockpit_status.get("headline"),
            "open_opportunities": ((cockpit_commercial.get("pipeline") or {}).get("open_opportunities")),
            "commercial_requires_attention": ((cockpit_commercial.get("pipeline") or {}).get("requires_attention")),
            "active_campaigns": cockpit_campaigns.get("active"),
            "campaigns_require_attention": cockpit_campaigns.get("requires_attention"),
        },
        "contracts": {
            "action_center_is_priority_authority": True,
            "selection_rule": "FIRST_N_CANONICAL_ACTION_CENTER_ITEMS",
            "max_visible_actions": 5,
            "canonical_order_preserved": True,
            "urgency_mapping_only": True,
            "no_reprioritization": True,
            "no_value_weighting": True,
            "no_due_date_reinterpretation": True,
            "completion_occurs_in_owner_module": True,
            "refresh_recomputes_from_canonical_state": True,
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
    """Terminal post-W99 runtime with a bounded operator-day projection."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def today_execution(self, company_id: str, *, limit: int = 5) -> dict:
        company = self.companies.get(company_id)
        action_center = self.action_center(company.id)
        cockpit = self.executive_cockpit(company.id)
        return compose_today_execution(
            company={"id": company.id, "name": company.name},
            action_center=action_center,
            cockpit=cockpit,
            limit=limit,
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds Today after Portfolio + Executive while preserving every prior route."""

    def _static(self, path: str) -> None:
        if path == "/executive-cockpit.js":
            target = self.server.runtime.repo_root / "web" / "executive-cockpit.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99TodayExecutionAfterExecutiveCockpit(){
  if(document.querySelector('script[data-post-w99-today-execution]'))return;
  const script=document.createElement('script');
  script.src='/today-execution.js';
  script.defer=true;
  script.dataset.postW99TodayExecution='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/today-execution.js":
            target = self.server.runtime.repo_root / "web" / "today-execution.js"
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
        if parsed.path == "/today-execution.js":
            self._static(parsed.path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "today-execution":
                self._json(self.server.runtime.today_execution(parts[2]))
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
    print(f"BINARIO Marketing App · post-W99 Today Execution: {url}")
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
    "AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve",
    "compose_today_execution",
]
