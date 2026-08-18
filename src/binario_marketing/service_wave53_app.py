from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .attribution_store import AttributionStore
from . import service_wave52_app as base


def _utm_slug(value: object, fallback: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9._~+-]+", "_", text).strip("_-.+")
    return (text[:150] or fallback[:150]).strip("_-.+")


def _value_bucket() -> dict:
    return {"open_count": 0, "won_count": 0, "lost_count": 0, "open_value": 0, "won_value": 0, "lost_value": 0}


def _add_opportunity(bucket: dict, opportunity) -> None:
    currency = opportunity.currency
    row = bucket.setdefault(currency, _value_bucket())
    value = int(opportunity.value or 0)
    if opportunity.stage == "WON":
        row["won_count"] += 1
        row["won_value"] += value
    elif opportunity.stage == "LOST":
        row["lost_count"] += 1
        row["lost_value"] += value
    else:
        row["open_count"] += 1
        row["open_value"] += value


class AppRuntime(base.AppRuntime):
    """Wave 53 adds deterministic first-party attribution without temporal guessing."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.attribution = AttributionStore(runtime.data_root / "State" / "attribution")
        return runtime

    def create_tracking_link(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("tracking link payload must be an object")
        company = self.companies.get(company_id)
        allowed = {
            "campaign_id", "creative_media_id", "destination_url", "utm_source", "utm_medium",
            "utm_campaign", "utm_id", "utm_content", "utm_term", "utm_source_platform",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported tracking link fields: {', '.join(sorted(unknown))}")
        campaign_id = str(payload.get("campaign_id") or "").strip()
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        media_id = str(payload.get("creative_media_id") or "").strip() or None
        creative = None
        if media_id:
            media = self.company_media.get_for_company(company.id, media_id)
            creative = self.creatives.get(company.id, media.id)
            if creative is None:
                raise ValueError("creative tracking requires a saved Creative Studio brief")
            if creative.campaign_id != campaign.id:
                raise ValueError("creative must be linked to the selected campaign")

        destination = str(payload.get("destination_url") or "").strip()
        if not destination and creative:
            destination = str(creative.destination_url or "").strip()
        if not destination:
            raise ValueError("destination_url is required; add it to the creative or this tracking link")
        source = _utm_slug(payload.get("utm_source"), "unknown")
        medium = _utm_slug(payload.get("utm_medium"), "unknown")
        if source == "unknown" or medium == "unknown":
            raise ValueError("utm_source and utm_medium are required")
        values = dict(payload)
        values.update({
            "campaign_id": campaign.id,
            "creative_media_id": media_id,
            "destination_url": destination,
            "utm_source": source,
            "utm_medium": medium,
            "utm_campaign": _utm_slug(payload.get("utm_campaign") or campaign.name, campaign.id),
            "utm_id": _utm_slug(payload.get("utm_id") or campaign.id, campaign.id),
            "utm_content": _utm_slug(payload.get("utm_content") or (media_id if media_id else "campaign"), "campaign"),
            "utm_source_platform": _utm_slug(payload.get("utm_source_platform") or source, source),
        })
        if payload.get("utm_term"):
            values["utm_term"] = _utm_slug(payload.get("utm_term"), "term")
        row = self.attribution.create_link(company.id, values)
        self.workspace.registries.timeline.append("attribution.tracking_link.created", {
            "company_id": company.id,
            "tracking_link_id": row.id,
            "campaign_id": row.campaign_id,
            "creative_media_id": row.creative_media_id,
            "utm_source": row.utm_source,
            "utm_medium": row.utm_medium,
            "provider_mutation_performed": False,
        })
        return asdict(row)

    def record_attribution_claim(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("attribution claim payload must be an object")
        company = self.companies.get(company_id)
        allowed = {"tracking_code", "contact_id", "opportunity_id", "evidence", "captured_at"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported attribution claim fields: {', '.join(sorted(unknown))}")
        code = str(payload.get("tracking_code") or "").strip()
        self.attribution.get_link_by_code(company.id, code)
        contact_id = str(payload.get("contact_id") or "").strip() or None
        opportunity_id = str(payload.get("opportunity_id") or "").strip() or None
        opportunity = None
        if opportunity_id:
            opportunity = self.crm.get_opportunity(opportunity_id)
            if opportunity.company_id != company.id:
                raise KeyError(opportunity_id)
            if not contact_id and opportunity.contact_id:
                contact_id = opportunity.contact_id
        if contact_id:
            contact = self.crm.get_contact(contact_id)
            if contact.company_id != company.id:
                raise KeyError(contact_id)
            if opportunity and opportunity.contact_id and opportunity.contact_id != contact.id:
                raise ValueError("contact does not match opportunity")
        values = dict(payload)
        values["tracking_code"] = code
        values["contact_id"] = contact_id
        values["opportunity_id"] = opportunity_id
        values["evidence"] = "CAPTURED_TRACKING_CODE"
        row = self.attribution.create_claim(company.id, values)
        link = self.attribution.get_link(company.id, row.tracking_link_id)
        self.workspace.registries.timeline.append("attribution.claim.recorded", {
            "company_id": company.id,
            "attribution_claim_id": row.id,
            "tracking_link_id": row.tracking_link_id,
            "campaign_id": link.campaign_id,
            "creative_media_id": link.creative_media_id,
            "contact_linked": bool(row.contact_id),
            "opportunity_linked": bool(row.opportunity_id),
            "evidence": row.evidence,
            "provider_mutation_performed": False,
        })
        return asdict(row)

    def _attribution_rollups(self, company_id: str) -> dict:
        links = self.attribution.list_links(company_id)
        claims = self.attribution.list_claims(company_id)
        link_by_id = {row.id: row for row in links}
        campaigns = {row.id: {
            "id": row.id,
            "name": row.name,
            "objective": row.objective,
            "tracking_links": 0,
            "touches": 0,
            "attributed_contacts": 0,
            "attributed_opportunities": 0,
            "attributed_won": 0,
            "value_by_currency": {},
        } for row in self.campaigns.list(company_id)}
        creatives = {}
        for row in self.creatives.list(company_id):
            creatives[row.media_id] = {
                "media_id": row.media_id,
                "title": row.title,
                "campaign_id": row.campaign_id,
                "tracking_links": 0,
                "touches": 0,
                "attributed_contacts": 0,
                "attributed_opportunities": 0,
                "attributed_won": 0,
                "value_by_currency": {},
            }

        for link in links:
            if link.campaign_id in campaigns:
                campaigns[link.campaign_id]["tracking_links"] += 1
            if link.creative_media_id in creatives:
                creatives[link.creative_media_id]["tracking_links"] += 1

        for claim in claims:
            link = link_by_id.get(claim.tracking_link_id)
            if not link:
                continue
            if link.campaign_id in campaigns:
                campaigns[link.campaign_id]["touches"] += 1
            if link.creative_media_id in creatives:
                creatives[link.creative_media_id]["touches"] += 1

        # A single CRM opportunity may legitimately capture multiple tracked touches.
        # Credit is therefore assigned once using the latest captured deterministic touch.
        primary_by_opportunity = {}
        primary_by_contact = {}
        for claim in claims:
            if claim.opportunity_id and claim.opportunity_id not in primary_by_opportunity:
                primary_by_opportunity[claim.opportunity_id] = claim
            if claim.contact_id and claim.contact_id not in primary_by_contact:
                primary_by_contact[claim.contact_id] = claim

        contact_sets_campaign: dict[str, set[str]] = {key: set() for key in campaigns}
        contact_sets_creative: dict[str, set[str]] = {key: set() for key in creatives}
        for contact_id, claim in primary_by_contact.items():
            link = link_by_id.get(claim.tracking_link_id)
            if not link:
                continue
            if link.campaign_id in contact_sets_campaign:
                contact_sets_campaign[link.campaign_id].add(contact_id)
            if link.creative_media_id in contact_sets_creative:
                contact_sets_creative[link.creative_media_id].add(contact_id)

        attributed_opportunities = []
        for opportunity_id, claim in primary_by_opportunity.items():
            try:
                opportunity = self.crm.get_opportunity(opportunity_id)
            except KeyError:
                continue
            if opportunity.company_id != company_id:
                continue
            link = link_by_id.get(claim.tracking_link_id)
            if not link:
                continue
            attributed_opportunities.append(opportunity)
            targets = []
            if link.campaign_id in campaigns:
                targets.append(campaigns[link.campaign_id])
            if link.creative_media_id in creatives:
                targets.append(creatives[link.creative_media_id])
            for target in targets:
                target["attributed_opportunities"] += 1
                if opportunity.stage == "WON":
                    target["attributed_won"] += 1
                _add_opportunity(target["value_by_currency"], opportunity)

        for key, values in contact_sets_campaign.items():
            campaigns[key]["attributed_contacts"] = len(values)
        for key, values in contact_sets_creative.items():
            creatives[key]["attributed_contacts"] = len(values)

        total_opportunities = len(self.crm.list_opportunities(company_id))
        total_contacts = len(self.crm.list_contacts(company_id))
        distinct_contacts = len(primary_by_contact)
        value_by_currency = {}
        attributed_won = 0
        for opportunity in attributed_opportunities:
            _add_opportunity(value_by_currency, opportunity)
            if opportunity.stage == "WON":
                attributed_won += 1
        coverage_percent = round(len(attributed_opportunities) * 100 / total_opportunities, 2) if total_opportunities else 0.0
        contact_coverage_percent = round(distinct_contacts * 100 / total_contacts, 2) if total_contacts else 0.0
        return {
            "campaigns": list(campaigns.values()),
            "creatives": list(creatives.values()),
            "summary": {
                "tracking_links": len(links),
                "captured_touches": len(claims),
                "attributed_contacts": distinct_contacts,
                "attributed_opportunities": len(attributed_opportunities),
                "attributed_won": attributed_won,
                "value_by_currency": value_by_currency,
            },
            "coverage": {
                "crm_contacts": total_contacts,
                "attributed_contacts": distinct_contacts,
                "contact_percent": contact_coverage_percent,
                "crm_opportunities": total_opportunities,
                "attributed_opportunities": len(attributed_opportunities),
                "opportunity_percent": coverage_percent,
            },
        }

    def attribution_payload(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        links = [asdict(row) for row in self.attribution.list_links(company.id)]
        claims = [asdict(row) for row in self.attribution.list_claims(company.id)]
        rollups = self._attribution_rollups(company.id)
        return {
            "schema": "binario.marketing.attribution-foundation.v1",
            "company_id": company.id,
            "summary": rollups["summary"],
            "coverage": rollups["coverage"],
            "campaigns": rollups["campaigns"],
            "creatives": rollups["creatives"],
            "tracking_links": links,
            "claims": claims,
            "model": {
                "tracking_parameter": "bm_tid",
                "crm_evidence": "CAPTURED_TRACKING_CODE",
                "opportunity_credit": "LAST_CAPTURED_TOUCH",
                "clicks_observed": False,
                "temporal_inference": False,
                "full_funnel_coverage_assumed": False,
                "note": "A generated URL is instrumentation, not click evidence. CRM credit exists only for records carrying a captured bm_tid.",
            },
            "safety": {
                "provider_call_performed": False,
                "provider_mutation_performed": False,
                "automatic_crm_mutation_performed": False,
                "automatic_attribution_performed": False,
            },
        }

    def learning_payload(self, company_id: str) -> dict:
        payload = super().learning_payload(company_id)
        attribution = self.attribution_payload(company_id)
        campaign_attr = {row["id"]: row for row in attribution["campaigns"]}
        creative_attr = {row["media_id"]: row for row in attribution["creatives"]}
        for row in payload.get("campaigns") or []:
            evidence = campaign_attr.get(row.get("id"))
            row["crm_attribution"] = evidence or {
                "attributed_contacts": 0, "attributed_opportunities": 0, "attributed_won": 0, "value_by_currency": {}
            }
        for row in payload.get("creatives") or []:
            evidence = creative_attr.get(row.get("media_id"))
            row["crm_attribution"] = evidence or {
                "attributed_contacts": 0, "attributed_opportunities": 0, "attributed_won": 0, "value_by_currency": {}
            }
        payload["attribution"]["crm_to_campaign_deterministic_partial"] = bool(attribution["summary"]["attributed_opportunities"])
        payload["attribution"]["crm_to_campaign_coverage_percent"] = attribution["coverage"]["opportunity_percent"]
        payload["attribution"]["crm_attribution_model"] = "LAST_CAPTURED_TOUCH"
        payload["attribution"]["note"] = "Only CRM records with an explicitly captured bm_tid are attributed; all other CRM outcomes remain unattributed."
        return payload

    def _ai_context(self, company_id: str, *, task: str, campaign_id: str | None, creative_media_id: str | None) -> dict:
        context = super()._ai_context(company_id, task=task, campaign_id=campaign_id, creative_media_id=creative_media_id)
        attribution = self.attribution_payload(company_id)
        context["attribution"] = {
            "model": {
                "crm_evidence": attribution["model"]["crm_evidence"],
                "opportunity_credit": attribution["model"]["opportunity_credit"],
                "temporal_inference": False,
                "full_funnel_coverage_assumed": False,
            },
            "summary": attribution["summary"],
            "coverage": attribution["coverage"],
            "campaigns": [{
                "id": row["id"],
                "name": row["name"],
                "objective": row["objective"],
                "attributed_contacts": row["attributed_contacts"],
                "attributed_opportunities": row["attributed_opportunities"],
                "attributed_won": row["attributed_won"],
                "value_by_currency": row["value_by_currency"],
            } for row in attribution["campaigns"] if row["touches"] or row["attributed_opportunities"]][:12],
            "creatives": [{
                "media_id": row["media_id"],
                "title": row["title"],
                "campaign_id": row["campaign_id"],
                "attributed_contacts": row["attributed_contacts"],
                "attributed_opportunities": row["attributed_opportunities"],
                "attributed_won": row["attributed_won"],
                "value_by_currency": row["value_by_currency"],
            } for row in attribution["creatives"] if row["touches"] or row["attributed_opportunities"]][:20],
        }
        return context


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/attribution-foundation.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "attribution":
                self._json(self.server.runtime.attribution_payload(parts[2]))
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["attribution", "links"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.create_tracking_link(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["attribution", "claims"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.record_attribution_claim(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_POST()


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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
