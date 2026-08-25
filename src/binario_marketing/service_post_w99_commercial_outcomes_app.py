from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_navigator_app as base


_CLOSED_CAMPAIGN_STATES = {"COMPLETED", "ARCHIVED", "CANCELLED"}


def _value_totals(value_by_currency: dict) -> tuple[int, int, int]:
    open_count = won_count = lost_count = 0
    for bucket in (value_by_currency or {}).values():
        open_count += int(bucket.get("open_count") or 0)
        won_count += int(bucket.get("won_count") or 0)
        lost_count += int(bucket.get("lost_count") or 0)
    return open_count, won_count, lost_count


def _next_action(*, campaign_status: str, tracking_links: int, captured_leads: int,
                 unresolved_leads: int, converted_without_opportunity: int,
                 value_by_currency: dict) -> dict:
    open_count, won_count, lost_count = _value_totals(value_by_currency)
    active = str(campaign_status or "").upper() not in _CLOSED_CAMPAIGN_STATES
    if unresolved_leads:
        return {
            "code": "RESOLVE_CAPTURED_LEADS", "priority": "HIGH",
            "label": "Resolver leads capturados", "view": "commercial-desk",
            "reason": f"Hay {unresolved_leads} lead(s) con tracking exacto aún sin conversión o descarte explícito.",
        }
    if converted_without_opportunity:
        return {
            "code": "CREATE_OPPORTUNITIES", "priority": "HIGH",
            "label": "Crear oportunidades", "view": "commercial-desk",
            "reason": f"Hay {converted_without_opportunity} lead(s) convertido(s) a contacto sin oportunidad comercial asociada.",
        }
    if open_count:
        return {
            "code": "ADVANCE_PIPELINE", "priority": "MEDIUM",
            "label": "Avanzar pipeline atribuido", "view": "crm", "tab": "pipeline",
            "reason": f"Hay {open_count} oportunidad(es) abierta(s) con atribución exacta a esta campaña.",
        }
    if lost_count and not won_count:
        return {
            "code": "REVIEW_LOSSES", "priority": "MEDIUM",
            "label": "Revisar pérdidas atribuidas", "view": "analytics",
            "reason": f"Hay {lost_count} oportunidad(es) perdida(s) atribuida(s); conviene revisar causa antes de decidir cambios de marketing.",
        }
    if won_count:
        return {
            "code": "REVIEW_WON_OUTCOME", "priority": "LOW",
            "label": "Revisar resultado ganado", "view": "analytics",
            "reason": f"Hay {won_count} oportunidad(es) ganada(s) atribuida(s) de forma determinística.",
        }
    if active and not tracking_links:
        return {
            "code": "INSTRUMENT_CAMPAIGN", "priority": "MEDIUM",
            "label": "Instrumentar campaña", "view": "analytics",
            "reason": "La campaña está activa pero no tiene links de tracking canónicos; no puede observarse el recorrido comercial first-party.",
        }
    if active and tracking_links and not captured_leads:
        return {
            "code": "CHECK_CAPTURE_COVERAGE", "priority": "LOW",
            "label": "Revisar cobertura de captura", "view": "analytics",
            "reason": "Existe instrumentación, pero todavía no hay leads first-party capturados con ese tracking. Esto no se interpreta como cero clics.",
        }
    return {
        "code": "NO_COMMERCIAL_SIGNAL", "priority": "LOW",
        "label": "Sin acción comercial urgente", "view": "analytics",
        "reason": "No hay una condición comercial determinística que requiera elevar prioridad en este momento.",
    }


def commercial_outcomes_projection(runtime, company_id: str) -> dict:
    """Build a deterministic campaign -> lead -> CRM outcome projection.

    Tracking links are instrumentation, not clicks. Attribution uses the canonical
    LAST_CAPTURED_TOUCH rollup and exact durable tracking identifiers only.
    """
    company = runtime.companies.get(company_id)
    campaigns = list(runtime.campaigns.list(company.id))
    links = list(runtime.attribution.list_links(company.id))
    leads = list(runtime.lead_intake.list(company.id))
    opportunities = {row.id: row for row in runtime.crm.list_opportunities(company.id)}
    attribution = runtime.attribution_payload(company.id)

    link_by_id = {row.id: row for row in links}
    link_by_code = {row.tracking_code: row for row in links}
    attributed_by_campaign = {row["id"]: row for row in attribution.get("campaigns") or []}

    campaign_rows: dict[str, dict] = {}
    for campaign in campaigns:
        attr = attributed_by_campaign.get(campaign.id) or {}
        value_by_currency = attr.get("value_by_currency") or {}
        campaign_rows[campaign.id] = {
            "campaign": {
                "id": campaign.id,
                "name": campaign.name,
                "objective": campaign.objective,
                "status": campaign.status,
                "channels": list(campaign.channels),
            },
            "funnel": {
                "tracking_links": 0,
                "captured_touches": int(attr.get("touches") or 0),
                "captured_leads": 0,
                "unresolved_captured_leads": 0,
                "converted_leads": 0,
                "converted_without_opportunity": 0,
                "converted_with_opportunity": 0,
                "attributed_contacts": int(attr.get("attributed_contacts") or 0),
                "attributed_opportunities": int(attr.get("attributed_opportunities") or 0),
                "attributed_won": int(attr.get("attributed_won") or 0),
            },
            "value_by_currency": value_by_currency,
            "journeys": [],
        }

    for link in links:
        row = campaign_rows.get(link.campaign_id)
        if row:
            row["funnel"]["tracking_links"] += 1

    captured_leads_total = converted_leads_total = converted_without_opportunity_total = 0
    for lead in leads:
        link = None
        if lead.tracking_link_id:
            link = link_by_id.get(lead.tracking_link_id)
        if link is None and lead.tracking_code:
            link = link_by_code.get(lead.tracking_code)
        if link is None:
            continue
        row = campaign_rows.get(link.campaign_id)
        if row is None:
            continue
        funnel = row["funnel"]
        funnel["captured_leads"] += 1
        captured_leads_total += 1
        converted = bool(lead.converted_contact_id)
        dismissed = bool(lead.dismissed_at)
        if converted:
            funnel["converted_leads"] += 1
            converted_leads_total += 1
            if lead.converted_opportunity_id:
                funnel["converted_with_opportunity"] += 1
            else:
                funnel["converted_without_opportunity"] += 1
                converted_without_opportunity_total += 1
        elif not dismissed:
            funnel["unresolved_captured_leads"] += 1

        opportunity = opportunities.get(lead.converted_opportunity_id) if lead.converted_opportunity_id else None
        row["journeys"].append({
            "lead_id": lead.id,
            "received_at": lead.received_at,
            "status": "DISMISSED" if dismissed else ("CONVERTED" if converted else "OPEN"),
            "contact_id": lead.converted_contact_id,
            "opportunity_id": lead.converted_opportunity_id,
            "opportunity": ({
                "stage": opportunity.stage,
                "value": opportunity.value,
                "currency": opportunity.currency,
            } if opportunity is not None else None),
            "evidence": "EXACT_TRACKING_LINK",
        })

    attention: list[dict] = []
    for campaign_id, row in campaign_rows.items():
        funnel = row["funnel"]
        action = _next_action(
            campaign_status=row["campaign"]["status"],
            tracking_links=funnel["tracking_links"],
            captured_leads=funnel["captured_leads"],
            unresolved_leads=funnel["unresolved_captured_leads"],
            converted_without_opportunity=funnel["converted_without_opportunity"],
            value_by_currency=row["value_by_currency"],
        )
        row["commercial_next_action"] = action
        open_count, won_count, lost_count = _value_totals(row["value_by_currency"])
        if won_count:
            state = "WON"
        elif open_count:
            state = "PIPELINE"
        elif lost_count:
            state = "LOST"
        elif funnel["converted_leads"]:
            state = "CONVERTED"
        elif funnel["captured_leads"]:
            state = "CAPTURED"
        elif funnel["tracking_links"]:
            state = "INSTRUMENTED"
        else:
            state = "UNINSTRUMENTED"
        row["commercial_state"] = state
        row["journeys"].sort(key=lambda item: (item.get("received_at") or "", item["lead_id"]), reverse=True)
        if action["priority"] in {"HIGH", "MEDIUM"}:
            attention.append({
                "campaign_id": campaign_id,
                "campaign_name": row["campaign"]["name"],
                "commercial_state": state,
                "action": action,
            })

    priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    attention.sort(key=lambda item: (priority_order.get(item["action"]["priority"], 9), item["campaign_name"].casefold(), item["campaign_id"]))
    ordered = sorted(campaign_rows.values(), key=lambda row: (priority_order.get(row["commercial_next_action"]["priority"], 9), row["campaign"]["name"].casefold(), row["campaign"]["id"]))
    attribution_summary = attribution.get("summary") or {}
    return {
        "schema": "binario.marketing.commercial-outcomes.v1",
        "company": {"id": company.id, "name": company.name},
        "summary": {
            "campaigns": len(ordered),
            "tracking_links": len(links),
            "captured_leads": captured_leads_total,
            "converted_leads": converted_leads_total,
            "converted_without_opportunity": converted_without_opportunity_total,
            "captured_touches": int(attribution_summary.get("captured_touches") or 0),
            "attributed_contacts": int(attribution_summary.get("attributed_contacts") or 0),
            "attributed_opportunities": int(attribution_summary.get("attributed_opportunities") or 0),
            "attributed_won": int(attribution_summary.get("attributed_won") or 0),
            "value_by_currency": attribution_summary.get("value_by_currency") or {},
            "attention": len(attention),
        },
        "attention": attention[:12],
        "campaigns": ordered,
        "model": {
            "campaign_to_lead": "EXACT_TRACKING_LINK",
            "crm_credit": "LAST_CAPTURED_TOUCH",
            "tracking_link_means_click": False,
            "temporal_inference": False,
            "name_or_date_matching": False,
            "currencies_combined": False,
            "probabilistic_forecast": False,
        },
        "contracts": {
            "instrumentation_is_not_outcome": True,
            "exact_tracking_only": True,
            "last_captured_touch": True,
            "lead_conversion_is_explicit": True,
            "currencies_remain_separate": True,
            "commercial_actions_are_deterministic": True,
            "human_decision_required": True,
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
    """Post-W99 chain with deterministic commercial outcome intelligence."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        return super().create(repo_root, data_root)

    def commercial_outcomes(self, company_id: str) -> dict:
        return commercial_outcomes_projection(self, company_id)

    def results_intelligence_workspace(self, company_id: str) -> dict:
        payload = super().results_intelligence_workspace(company_id)
        outcomes = self.commercial_outcomes(company_id)
        by_campaign = {row["campaign"]["id"]: row for row in outcomes["campaigns"]}
        for row in payload.get("campaigns") or []:
            campaign_id = (row.get("campaign") or {}).get("id")
            outcome = by_campaign.get(campaign_id)
            if outcome is None:
                continue
            row["commercial_outcome"] = {
                "state": outcome["commercial_state"],
                "funnel": outcome["funnel"],
                "value_by_currency": outcome["value_by_currency"],
                "next_action": outcome["commercial_next_action"],
            }
        payload["commercial_outcomes"] = {
            "schema": outcomes["schema"],
            "summary": outcomes["summary"],
            "model": outcomes["model"],
            "contracts": outcomes["contracts"],
        }
        return payload

    def marketing_command_center(self, company_id: str) -> dict:
        payload = super().marketing_command_center(company_id)
        outcomes = self.commercial_outcomes(company_id)
        payload["commercial_outcomes"] = {
            "schema": outcomes["schema"],
            "summary": outcomes["summary"],
            "attention": outcomes["attention"][:5],
            "model": outcomes["model"],
        }
        return payload


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path == "/navigator.js":
            target = self.server.runtime.repo_root / "web" / "navigator.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99CommercialOutcomes(){
  if(document.querySelector('script[data-post-w99-commercial-outcomes]'))return;
  const script=document.createElement('script');
  script.src='/commercial-outcomes.js';
  script.defer=true;
  script.dataset.postW99CommercialOutcomes='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/commercial-outcomes.js":
            self._static(parsed.path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "commercial-outcomes":
                self._json(self.server.runtime.commercial_outcomes(parts[2]))
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
    print(f"BINARIO Marketing App · post-W99 Commercial Outcomes: {url}")
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


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "commercial_outcomes_projection", "create_server", "serve"]
