from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave61_app as base


_CLOSED_OPPORTUNITY_STAGES = {"WON", "LOST"}


def _moment(value: object) -> datetime | None:
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


class AppRuntime(base.AppRuntime):
    """Wave 62 composes a local, evidence-based 360° commercial contact view."""

    def contact_360(self, company_id: str, contact_id: str) -> dict:
        company = self.companies.get(company_id)
        detail = self.crm.contact_detail(company.id, contact_id)
        contact = detail["contact"]
        opportunities = list(detail.get("opportunities") or [])
        activities = list(detail.get("activities") or [])
        opportunity_ids = {row["id"] for row in opportunities}

        lead_origins: list[dict] = []
        for lead in self.lead_intake.list(company.id):
            if lead.converted_contact_id != contact_id:
                continue
            lead_origins.append({
                "lead_id": lead.id,
                "connector": lead.connector,
                "source_ref": lead.source_ref,
                "source": lead.source,
                "received_at": lead.received_at,
                "converted_at": lead.converted_at,
                "converted_opportunity_id": lead.converted_opportunity_id,
                "attribution_verified": bool(lead.tracking_code and lead.tracking_link_id),
                "utm_source": lead.utm_source,
                "utm_medium": lead.utm_medium,
                "utm_campaign": lead.utm_campaign,
                "utm_content": lead.utm_content,
                "utm_source_platform": lead.utm_source_platform,
            })
        lead_origins.sort(key=lambda row: (row.get("received_at") or "", row["lead_id"]), reverse=True)

        links = {row.id: row for row in self.attribution.list_links(company.id)}
        claims = []
        attributed_campaign_ids: set[str] = set()
        for claim in self.attribution.list_claims(company.id):
            if claim.contact_id != contact_id and claim.opportunity_id not in opportunity_ids:
                continue
            link = links.get(claim.tracking_link_id)
            if link is None:
                continue
            attributed_campaign_ids.add(link.campaign_id)
            claims.append({
                "claim_id": claim.id,
                "evidence": claim.evidence,
                "captured_at": claim.captured_at,
                "contact_id": claim.contact_id,
                "opportunity_id": claim.opportunity_id,
                "campaign_id": link.campaign_id,
                "creative_media_id": link.creative_media_id,
                "utm_source": link.utm_source,
                "utm_medium": link.utm_medium,
                "utm_campaign": link.utm_campaign,
                "utm_id": link.utm_id,
                "utm_content": link.utm_content,
                "utm_term": link.utm_term,
                "utm_source_platform": link.utm_source_platform,
            })
        claims.sort(key=lambda row: (row.get("captured_at") or "", row["claim_id"]), reverse=True)

        campaign_rows = []
        for campaign in self.campaigns.list(company.id):
            audience_membership = contact_id in campaign.audience_contact_ids
            attribution_evidence = campaign.id in attributed_campaign_ids
            if not audience_membership and not attribution_evidence:
                continue
            campaign_rows.append({
                "id": campaign.id,
                "name": campaign.name,
                "objective": campaign.objective,
                "status": campaign.status,
                "start_at": campaign.start_at,
                "end_at": campaign.end_at,
                "channels": list(campaign.channels),
                "audience_membership": audience_membership,
                "attribution_evidence": attribution_evidence,
            })

        now = datetime.now(timezone.utc)
        pending_activities = [row for row in activities if not row.get("completed_at")]
        overdue_activities = [
            row for row in pending_activities
            if _moment(row.get("due_at")) is not None and _moment(row.get("due_at")) < now
        ]
        open_opportunities = [row for row in opportunities if row.get("stage") not in _CLOSED_OPPORTUNITY_STAGES]
        won_opportunities = [row for row in opportunities if row.get("stage") == "WON"]

        overdue_activities.sort(key=lambda row: (_moment(row.get("due_at")) or now, row["id"]))
        pending_activities.sort(key=lambda row: (row.get("due_at") or "9999", row.get("created_at") or "", row["id"]))
        open_opportunities.sort(key=lambda row: (row.get("updated_at") or "", row["id"]), reverse=True)

        if overdue_activities:
            row = overdue_activities[0]
            next_action = {
                "code": "RESOLVE_OVERDUE_FOLLOWUP",
                "label": "Resolver seguimiento vencido",
                "reason": row.get("summary") or "Hay una actividad comercial vencida.",
                "activity_id": row["id"],
                "opportunity_id": row.get("opportunity_id"),
            }
        elif pending_activities:
            row = pending_activities[0]
            next_action = {
                "code": "FOLLOW_UP_AS_PLANNED",
                "label": "Revisar seguimiento programado",
                "reason": row.get("summary") or "Ya existe una actividad comercial pendiente.",
                "activity_id": row["id"],
                "opportunity_id": row.get("opportunity_id"),
            }
        elif open_opportunities:
            row = open_opportunities[0]
            next_action = {
                "code": "PLAN_FOLLOWUP",
                "label": "Programar siguiente seguimiento",
                "reason": "La oportunidad está abierta y no tiene una actividad pendiente.",
                "activity_id": None,
                "opportunity_id": row["id"],
            }
        elif lead_origins:
            next_action = {
                "code": "CREATE_OPPORTUNITY",
                "label": "Crear oportunidad",
                "reason": "El contacto proviene de Lead Intake y no tiene una oportunidad abierta.",
                "activity_id": None,
                "opportunity_id": None,
            }
        else:
            next_action = {
                "code": "REVIEW_RELATIONSHIP",
                "label": "Revisar relación comercial",
                "reason": "No hay una siguiente acción pendiente inferible desde el estado local.",
                "activity_id": None,
                "opportunity_id": None,
            }

        timeline: list[dict] = []
        for row in lead_origins:
            timeline.append({
                "kind": "LEAD_RECEIVED",
                "at": row.get("received_at"),
                "label": f"Lead recibido · {row.get('connector') or 'INTAKE'}",
                "ref_id": row["lead_id"],
            })
            if row.get("converted_at"):
                timeline.append({
                    "kind": "LEAD_CONVERTED",
                    "at": row.get("converted_at"),
                    "label": "Lead convertido explícitamente a CRM",
                    "ref_id": row["lead_id"],
                })
        for row in opportunities:
            timeline.append({
                "kind": "OPPORTUNITY_CREATED",
                "at": row.get("created_at"),
                "label": f"Oportunidad · {row.get('title') or row['id']} · {row.get('stage')}",
                "ref_id": row["id"],
            })
        for row in activities:
            timeline.append({
                "kind": "ACTIVITY_CREATED",
                "at": row.get("created_at"),
                "label": f"{row.get('kind')} · {row.get('summary')}",
                "ref_id": row["id"],
            })
            if row.get("completed_at"):
                timeline.append({
                    "kind": "ACTIVITY_COMPLETED",
                    "at": row.get("completed_at"),
                    "label": f"Actividad completada · {row.get('summary')}",
                    "ref_id": row["id"],
                })
        for row in claims:
            timeline.append({
                "kind": "ATTRIBUTION_CAPTURED",
                "at": row.get("captured_at"),
                "label": "Atribución capturada con evidencia first-party",
                "ref_id": row["claim_id"],
            })
        timeline.sort(key=lambda row: (row.get("at") or "", row.get("ref_id") or ""), reverse=True)

        return {
            "schema": "binario.marketing.contact-360.v1",
            "company": {"id": company.id, "name": company.name},
            "contact": contact,
            "summary": {
                "opportunities": len(opportunities),
                "open_opportunities": len(open_opportunities),
                "won_opportunities": len(won_opportunities),
                "activities": len(activities),
                "pending_activities": len(pending_activities),
                "overdue_activities": len(overdue_activities),
                "lead_origins": len(lead_origins),
                "attribution_claims": len(claims),
                "campaigns": len(campaign_rows),
            },
            "next_action": next_action,
            "opportunities": opportunities,
            "activities": activities,
            "lead_origins": lead_origins,
            "attribution": claims,
            "campaigns": campaign_rows,
            "timeline": timeline[:100],
            "evidence_contract": {
                "lead_origin": "DURABLE_LEAD_INTAKE",
                "attribution": "CAPTURED_TRACKING_CODE_ONLY",
                "campaign_membership": "AUDIENCE_SNAPSHOT_OR_ATTRIBUTION_EVIDENCE",
                "provider_inference": False,
            },
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "automatic_action_execution": False,
                "automatic_message_send": False,
                "background_polling": False,
                "fuzzy_identity_guessing": False,
                "cloud_required": False,
                "tracking_code_exposed": False,
                "tracked_url_exposed": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 62 adds only local GET composition and one bundled browser asset."""

    def _wave62_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/contact-360.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "contacts"
                and parts[5] == "360"
            ):
                self._json(self.server.runtime.contact_360(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave62_error(exc)
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
