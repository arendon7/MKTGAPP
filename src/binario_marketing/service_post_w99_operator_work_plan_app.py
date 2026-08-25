from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_integrated_cockpit_app as base


_BUCKETS = {"CRITICAL": "NOW", "HIGH": "NOW", "MEDIUM": "NEXT", "LOW": "LATER"}


def _text(value: object, fallback: str = "") -> str:
    value = str(value or "").strip()
    return value or fallback


def _copy_action(row: dict) -> dict:
    action = row.get("action") or {}
    return {
        "label": action.get("label"),
        "view": action.get("view"),
        "tab": action.get("tab"),
        "entity_id": action.get("entity_id"),
        "lead_id": action.get("lead_id"),
        "contact_id": action.get("contact_id"),
        "opportunity_id": action.get("opportunity_id"),
        "campaign_id": action.get("campaign_id"),
        "media_id": action.get("media_id"),
    }


def compose_operator_work_plan(
    *, company: dict, action_center: dict, cockpit: dict, generated_at: str | None = None
) -> dict:
    """Project Action Center order into an explicit human operating sequence.

    The function never creates task ownership, dates, priority scores, provider reads or
    business mutations. Action Center remains the sole ordering authority.
    """
    queue = list(action_center.get("queue") or [])
    sequence: list[dict] = []
    counts = {"NOW": 0, "NEXT": 0, "LATER": 0}
    source_counts: dict[str, int] = {}

    for position, row in enumerate(queue, start=1):
        urgency = _text(row.get("urgency"), "LOW").upper()
        bucket = _BUCKETS.get(urgency, "LATER")
        counts[bucket] += 1
        source = _text(row.get("source"), "UNKNOWN").upper()
        source_counts[source] = source_counts.get(source, 0) + 1
        due_at = row.get("due_at")
        sequence.append(
            {
                "sequence": position,
                "action_center_id": row.get("id"),
                "bucket": bucket,
                "urgency": urgency,
                "source": source,
                "kind": row.get("kind"),
                "title": row.get("title"),
                "detail": row.get("detail"),
                "blocking": bool(row.get("blocking")),
                "reason": dict(row.get("reason") or {}),
                "action": _copy_action(row),
                "schedule": {
                    "due_at": due_at,
                    "explicit_due_at_present": bool(due_at),
                    "due_at_invented": False,
                },
                "human_execution_required": True,
                "task_created": False,
                "priority_recomputed": False,
            }
        )

    sections = {
        "now": [row for row in sequence if row["bucket"] == "NOW"],
        "next": [row for row in sequence if row["bucket"] == "NEXT"],
        "later": [row for row in sequence if row["bucket"] == "LATER"],
    }
    cockpit_status = cockpit.get("status") or {}
    cockpit_lanes = [
        {
            "key": row.get("key"),
            "label": row.get("label"),
            "state": row.get("state"),
            "headline": row.get("headline"),
        }
        for row in cockpit.get("lanes") or []
    ]
    blocking = sum(1 for row in sequence if row["blocking"])
    first = sequence[0] if sequence else None

    brief = []
    if first:
        brief.append(
            {
                "code": "START_WITH_ACTION_CENTER_TOP",
                "label": "Primera acción",
                "text": first.get("title"),
                "detail": "Es el primer elemento del Action Center; el plan no cambia su prioridad.",
            }
        )
    if blocking:
        brief.append(
            {
                "code": "BLOCKERS_PRESENT",
                "label": "Bloqueos",
                "text": f"{blocking} elemento(s) bloqueante(s)",
                "detail": "Los bloqueos ya estaban marcados por las superficies canónicas; aquí solo se hacen visibles en secuencia.",
            }
        )
    if counts["NEXT"] or counts["LATER"]:
        brief.append(
            {
                "code": "FOLLOW_ON_WORK_VISIBLE",
                "label": "Continuidad",
                "text": f"{counts['NEXT']} después · {counts['LATER']} más tarde",
                "detail": "La continuidad conserva el orden completo de Action Center y no impone capacidad diaria artificial.",
            }
        )

    return {
        "schema": "binario.marketing.operator-work-plan.v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "company": {"id": company.get("id"), "name": company.get("name")},
        "summary": {
            "total": len(sequence),
            "now": counts["NOW"],
            "next": counts["NEXT"],
            "later": counts["LATER"],
            "blocking": blocking,
            "by_source": source_counts,
        },
        "first_action": first,
        "brief": brief,
        "sections": sections,
        "sequence": sequence,
        "executive_context": {
            "state": cockpit_status.get("state"),
            "headline": cockpit_status.get("headline"),
            "lanes": cockpit_lanes,
            "affects_priority_order": False,
        },
        "contracts": {
            "action_center_is_priority_authority": True,
            "exact_action_center_order_preserved": True,
            "urgency_bucket_mapping_only": True,
            "no_task_store_created": True,
            "no_task_ownership_invented": True,
            "no_due_dates_invented": True,
            "no_capacity_assumption": True,
            "human_execution_required": True,
        },
        "safety": {
            "read_only_projection": True,
            "business_mutation_performed": False,
            "provider_read_performed": False,
            "provider_mutation_performed": False,
            "ai_generation_performed": False,
            "automatic_execution": False,
            "background_polling": False,
            "cloud_required": False,
        },
    }


class AppRuntime(base.AppRuntime):
    """Terminal post-W99 runtime adding a read-only operating sequence."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def operator_work_plan(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return compose_operator_work_plan(
            company={"id": company.id, "name": company.name},
            action_center=self.action_center(company.id),
            cockpit=self.executive_cockpit(company.id),
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Expose the work plan as GET-only and append its UI after Executive Cockpit."""

    def _static(self, path: str) -> None:
        if path == "/executive-cockpit.js":
            target = self.server.runtime.repo_root / "web" / "executive-cockpit.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99OperatorWorkPlanAfterCockpit(){
  if(document.querySelector('script[data-post-w99-operator-work-plan]'))return;
  const script=document.createElement('script');
  script.src='/operator-work-plan.js';
  script.defer=true;
  script.dataset.postW99OperatorWorkPlan='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/operator-work-plan.js":
            target = self.server.runtime.repo_root / "web" / "operator-work-plan.js"
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
        if parsed.path == "/operator-work-plan.js":
            self._static(parsed.path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "operator-work-plan":
                self._json(self.server.runtime.operator_work_plan(parts[2]))
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
    print(f"BINARIO Marketing App · post-W99 Operator Work Plan: {url}")
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
    "AppRuntime", "MarketingHandler", "MarketingHTTPServer", "compose_operator_work_plan", "create_server", "serve"
]
