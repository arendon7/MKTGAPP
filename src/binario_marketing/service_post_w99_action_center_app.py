from __future__ import annotations

from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave76_app as base


_URGENCY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}


def _text(value: object, fallback: str = "") -> str:
    value = str(value or "").strip()
    return value or fallback


def _stable_id(*parts: object) -> str:
    clean = []
    for part in parts:
        value = _text(part, "none").lower()
        value = "".join(ch if ch.isalnum() or ch in "-_.:" else "-" for ch in value)
        clean.append(value[:100])
    return ":".join(clean)


def _item(
    *, rank: int, urgency: str, source: str, kind: str, title: str, detail: str,
    action_label: str, view: str, reason_code: str, reason: str,
    due_at: str | None = None, tab: str | None = None, entity_id: str | None = None,
    lead_id: str | None = None, contact_id: str | None = None,
    opportunity_id: str | None = None, campaign_id: str | None = None,
    media_id: str | None = None, blocking: bool = False,
) -> dict:
    return {
        "id": _stable_id(source, kind, entity_id or lead_id or campaign_id or opportunity_id or contact_id or title),
        "rank": int(rank), "urgency": urgency, "source": source, "kind": kind,
        "title": title, "detail": detail,
        "action": {"label": action_label, "view": view, "tab": tab, "entity_id": entity_id,
                   "lead_id": lead_id, "contact_id": contact_id, "opportunity_id": opportunity_id,
                   "campaign_id": campaign_id, "media_id": media_id},
        "reason": {"code": reason_code, "explanation": reason},
        "due_at": due_at, "blocking": bool(blocking),
        "requires_human_action": True, "read_only_recommendation": True,
    }


def compose_action_center(*, company: dict, workdesk: dict, commercial: dict, execution: dict,
                          results: dict, command: dict, generated_at: str | None = None) -> dict:
    """Compose one explainable queue from already-certified local projections.

    Pure by design: no providers, mutations, AI generation, or execution of recommendations.
    """
    queue: list[dict] = []
    workdesk_publication_failure = False
    workdesk_rank = {
        "publication_failed": (0, "CRITICAL", True, "Resolver publicación"),
        "publication_overdue": (10, "CRITICAL", True, "Revisar calendario"),
        "crm_overdue": (20, "HIGH", False, "Abrir seguimiento"),
        "crm_today": (35, "HIGH", False, "Abrir seguimiento"),
        "publication_today": (40, "HIGH", False, "Abrir calendario"),
        "crm_unscheduled": (55, "MEDIUM", False, "Programar seguimiento"),
    }
    for row in workdesk.get("queue") or []:
        kind = _text(row.get("kind"), "workdesk")
        rank, urgency, blocking, action_label = workdesk_rank.get(kind, (60, "MEDIUM", False, "Abrir"))
        if kind == "publication_failed": workdesk_publication_failure = True
        queue.append(_item(
            rank=rank, urgency=urgency, source="OPERATIONS", kind=kind,
            title=_text(row.get("title"), "Tarea operativa"),
            detail=_text(row.get("detail"), "Revisar el estado local"),
            action_label=action_label, view=_text(row.get("view"), "home"), tab=row.get("tab"),
            entity_id=row.get("entity_id"), contact_id=row.get("contact_id"),
            opportunity_id=row.get("opportunity_id"), due_at=row.get("due_at"), blocking=blocking,
            reason_code=f"WORKDESK_{kind.upper()}",
            reason="La mesa diaria ya marcó este elemento por fecha o estado local; Action Center solo lo eleva a la cola global.",
        ))

    lead_rank = {"CONFLICT": 22, "MATCHED": 24, "NEW": 28, "UNIDENTIFIED": 30}
    lead_labels = {"CONFLICT": "Resolver identidad exacta", "MATCHED": "Confirmar coincidencia exacta",
                   "NEW": "Crear contacto", "UNIDENTIFIED": "Resolver lead"}
    for row in commercial.get("lead_queue") or []:
        status = _text(row.get("status"), "NEW").upper()
        queue.append(_item(
            rank=lead_rank.get(status, 31), urgency="HIGH", source="COMMERCIAL",
            kind=f"lead_{status.lower()}",
            title=f"{lead_labels.get(status, 'Resolver lead')} · {_text(row.get('display_name'), 'Lead sin nombre')}",
            detail=(f"{_text(row.get('connector'), 'Lead Intake')} · {int(row.get('exact_match_count') or 0)} "
                    f"coincidencia(s) exacta(s) · {int(row.get('duplicate_open_lead_count') or 0)} duplicado(s) abierto(s)"),
            action_label="Abrir mesa comercial", view="commercial-desk", lead_id=row.get("lead_id"),
            due_at=row.get("received_at"), blocking=status == "CONFLICT", reason_code=f"LEAD_{status}",
            reason="El lead aún requiere una decisión humana de identidad o conversión; no se permite matching difuso ni conversión automática.",
        ))

    for row in commercial.get("handoffs") or []:
        state = _text(row.get("handoff_state")).upper()
        if state not in {"NEEDS_OPPORTUNITY", "NEEDS_FOLLOWUP"}: continue
        needs_opportunity = state == "NEEDS_OPPORTUNITY"
        queue.append(_item(
            rank=32 if needs_opportunity else 33, urgency="HIGH", source="COMMERCIAL", kind=state.lower(),
            title=("Crear oportunidad" if needs_opportunity else "Programar siguiente seguimiento") +
                  f" · {_text(row.get('contact_name'), 'Contacto')}",
            detail=_text(row.get("opportunity_title"), "El lead ya fue convertido, pero el handoff comercial todavía está incompleto."),
            action_label="Abrir mesa comercial", view="commercial-desk", lead_id=row.get("lead_id"),
            contact_id=row.get("contact_id"), opportunity_id=row.get("opportunity_id"), reason_code=state,
            reason="La conversión a CRM existe, pero falta el siguiente objeto comercial explícito para que el proceso no quede sin dueño.",
        ))

    result_priority = {
        "FIX_EXECUTION": (5, "CRITICAL", True), "CAPTURE_RESULTS": (44, "MEDIUM", False),
        "REVIEW_COVERAGE": (46, "MEDIUM", False), "RECORD_DECISION": (48, "MEDIUM", False),
        "CREATE_CREATIVE": (50, "MEDIUM", False), "FINISH_CREATIVE": (51, "MEDIUM", False),
        "PREPARE_DISTRIBUTION": (52, "MEDIUM", False), "SCHEDULE_OR_PUBLISH": (53, "MEDIUM", False),
        "REVIEW_PAID": (54, "MEDIUM", False), "DEFINE_CHANNELS": (54, "MEDIUM", False),
        "OPTIONAL_AI": (88, "LOW", False), "REVIEW_RESULTS": (72, "LOW", False),
        "CALENDAR": (73, "LOW", False), "COORDINATE": (74, "LOW", False),
        "PLANNED_ONLY": (90, "LOW", False), "COMPLETE": (95, "LOW", False),
    }
    result_rows = list(results.get("campaigns") or [])
    if not result_rows:
        result_rows = [
            {"campaign": row.get("campaign") or {}, "evidence": {"summary": "Sin lectura de resultados; se conserva la siguiente acción de ejecución."},
             "next_action": row.get("next_action") or {}}
            for row in execution.get("campaigns") or []
        ]
    active_campaigns = 0; campaign_actions = 0
    for row in result_rows:
        campaign = row.get("campaign") or {}
        if _text(campaign.get("status")).upper() in {"COMPLETED", "ARCHIVED"}: continue
        active_campaigns += 1
        next_action = row.get("next_action") or {}; code = _text(next_action.get("code"), "EXECUTION").upper()
        if code == "FIX_EXECUTION" and workdesk_publication_failure: continue
        rank, urgency, blocking = result_priority.get(code, (65, "MEDIUM", False))
        label = _text(next_action.get("label"), "Continuar campaña")
        evidence = row.get("evidence") or {}
        queue.append(_item(
            rank=rank, urgency=urgency, source="CAMPAIGN", kind=code.lower(),
            title=f"{label} · {_text(campaign.get('name'), 'Campaña')}",
            detail=_text(evidence.get("summary"), f"Campaña {_text(campaign.get('status'), 'activa')}"),
            action_label=label, view=_text(next_action.get("view"), "execution"),
            campaign_id=campaign.get("id"), media_id=next_action.get("media_id"), blocking=blocking,
            reason_code=f"CAMPAIGN_{code}",
            reason="Results Intelligence cruza ejecución, evidencia, atribución y decisión humana; Action Center conserva esa recomendación sin ejecutarla.",
        )); campaign_actions += 1

    setup_seen: set[str] = set(); product_gaps = list(workdesk.get("product_gaps") or [])
    if not product_gaps:
        product_gaps = [row for row in command.get("priorities") or [] if int(row.get("level") or 0) >= 5][:8]
    for row in product_gaps:
        code = _text(row.get("code") or row.get("kind") or row.get("title"), "setup").upper()
        if code in setup_seen: continue
        setup_seen.add(code)
        queue.append(_item(
            rank=82, urgency="LOW", source="SETUP", kind=code.lower(),
            title=_text(row.get("title") or row.get("label"), "Completar configuración"),
            detail=_text(row.get("detail") or row.get("message"), "Hay una brecha de preparación del producto."),
            action_label="Revisar configuración", view=_text(row.get("view"), "companies"),
            reason_code=f"SETUP_{code}",
            reason="La brecha proviene del Command Center y se mantiene debajo del trabajo operativo y comercial activo.",
        ))

    deduped: dict[str, dict] = {}
    for row in queue:
        current = deduped.get(row["id"])
        if current is None or (row["rank"], _URGENCY_ORDER[row["urgency"]]) < (current["rank"], _URGENCY_ORDER[current["urgency"]]):
            deduped[row["id"]] = row
    queue = list(deduped.values())
    queue.sort(key=lambda row: (row["rank"], _URGENCY_ORDER.get(row["urgency"], 9), row.get("due_at") is None,
                                row.get("due_at") or "", row["id"]))
    queue = queue[:50]
    counts_by_source = {key: 0 for key in ("OPERATIONS", "COMMERCIAL", "CAMPAIGN", "SETUP")}
    counts_by_urgency = {key: 0 for key in ("CRITICAL", "HIGH", "MEDIUM", "LOW")}
    for row in queue:
        counts_by_source[row["source"]] = counts_by_source.get(row["source"], 0) + 1
        counts_by_urgency[row["urgency"]] = counts_by_urgency.get(row["urgency"], 0) + 1
    return {
        "schema": "binario.marketing.action-center.v1",
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "company": {"id": company.get("id"), "name": company.get("name")},
        "next_action": queue[0] if queue else None,
        "summary": {"queue_total": len(queue), "blocking": sum(1 for row in queue if row["blocking"]),
                    "critical": counts_by_urgency["CRITICAL"], "high": counts_by_urgency["HIGH"],
                    "medium": counts_by_urgency["MEDIUM"], "low": counts_by_urgency["LOW"],
                    "by_source": counts_by_source, "active_campaigns": active_campaigns,
                    "campaign_actions": campaign_actions},
        "focus": {"now": [r for r in queue if r["urgency"] in {"CRITICAL", "HIGH"}][:8],
                  "next": [r for r in queue if r["urgency"] == "MEDIUM"][:8],
                  "later": [r for r in queue if r["urgency"] == "LOW"][:8]},
        "queue": queue,
        "contracts": {"single_cross_module_priority_queue": True,
                      "existing_canonical_surfaces_are_authoritative": True,
                      "recommendations_are_explainable": True, "human_execution_required": True,
                      "no_provider_side_effects": True, "no_ai_side_effects": True},
        "safety": {"read_only_projection": True, "business_mutation_performed": False,
                   "provider_read_performed": False, "provider_mutation_performed": False,
                   "ai_generation_performed": False, "automatic_execution": False,
                   "background_polling": False, "cloud_required": False},
    }


class AppRuntime(base.AppRuntime):
    """Post-W99 product branch: unify existing local recommendations without new authority."""
    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def action_center(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        return compose_action_center(
            company={"id": company.id, "name": company.name}, workdesk=self.daily_workdesk(company.id),
            commercial=self.commercial_desk(company.id), execution=self.campaign_execution_workspace(company.id),
            results=self.results_intelligence_workspace(company.id), command=self.marketing_command_center(company.id),
        )


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds one GET-only product projection and its companion UI."""
    def _action_center_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError): self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)): self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else: self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/uat-functional-journey.js":
            target = self.server.runtime.repo_root / "web" / "uat-functional-journey.js"
            if not target.is_file(): self._error(HTTPStatus.NOT_FOUND, "not found"); return
            bootstrap = """
;(function loadPostW99ActionCenter(){
  if(document.querySelector('script[data-post-w99-action-center]'))return;
  const actionCenter=document.createElement('script');
  actionCenter.src='/action-center.js';
  actionCenter.defer=true;
  actionCenter.dataset.postW99ActionCenter='1';
  document.head.append(actionCenter);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body)); self.wfile.write(body); return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/action-center.js": self._static(path); return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "action-center":
                self._json(self.server.runtime.action_center(parts[2])); return
        except Exception as exc:
            self._action_center_error(exc); return
        super().do_GET()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create(); server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]; url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App · post-W99 Action Center: {url}"); print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "compose_action_center", "create_server", "serve"]
