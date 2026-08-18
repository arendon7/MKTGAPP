from __future__ import annotations

import hashlib
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .lead_intake_store import (
    LEAD_CONNECTORS,
    MAX_LEAD_CSV_BYTES,
    LeadIntakeStore,
    identity_keys,
    parse_lead_csv,
)
from .social_store import _assert_secret_free, _now
from . import service_wave54_app as base


_CONTACT_INPUT_FIELDS = {
    "name", "organization", "role", "email", "phone", "whatsapp",
    "instagram", "source", "tags", "notes",
}
_OPPORTUNITY_INPUT_FIELDS = {
    "title", "stage", "value", "currency", "next_action", "next_action_at", "notes",
}


class AppRuntime(base.AppRuntime):
    """Wave 55 stages inbound leads before any explicit CRM conversion."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.lead_intake = LeadIntakeStore(runtime.data_root / "State" / "lead-intake")
        return runtime

    @staticmethod
    def _contact_identity_keys(contact) -> set[tuple[str, str]]:
        return set(identity_keys(asdict(contact)))

    def _lead_exact_matches(self, company_id: str, lead) -> list:
        lead_keys = set(identity_keys(asdict(lead)))
        if not lead_keys:
            return []
        matches = []
        for contact in self.crm.list_contacts(company_id):
            if lead_keys & self._contact_identity_keys(contact):
                matches.append(contact)
        return matches

    def _duplicate_open_leads(self, company_id: str, lead) -> list[str]:
        if lead.converted_contact_id or lead.dismissed_at:
            return []
        lead_keys = set(identity_keys(asdict(lead)))
        if not lead_keys:
            return []
        result: list[str] = []
        for other in self.lead_intake.list(company_id):
            if other.id == lead.id or other.converted_contact_id or other.dismissed_at:
                continue
            if lead_keys & set(identity_keys(asdict(other))):
                result.append(other.id)
        return sorted(result)

    def _lead_payload(self, company_id: str, lead) -> dict:
        matches = self._lead_exact_matches(company_id, lead)
        duplicate_ids = self._duplicate_open_leads(company_id, lead)
        if lead.dismissed_at:
            status = "DISMISSED"
        elif lead.converted_contact_id:
            status = "CONVERTED"
        elif len(matches) > 1:
            status = "CONFLICT"
        elif len(matches) == 1:
            status = "MATCHED"
        elif identity_keys(asdict(lead)):
            status = "NEW"
        else:
            status = "UNIDENTIFIED"
        payload = asdict(lead)
        payload["status"] = status
        payload["identity_keys_present"] = sorted({kind for kind, _ in identity_keys(asdict(lead))})
        payload["candidate_contacts"] = [{
            "id": row.id,
            "name": row.name,
            "organization": row.organization,
            "email": row.email,
            "phone": row.phone,
            "whatsapp": row.whatsapp,
            "instagram": row.instagram,
        } for row in matches]
        payload["exact_match_count"] = len(matches)
        payload["duplicate_open_lead_ids"] = duplicate_ids
        payload["duplicate_open_lead_count"] = len(duplicate_ids)
        payload["attribution_verified"] = bool(lead.tracking_code and lead.tracking_link_id)
        return payload

    def lead_intake_payload(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        rows = [self._lead_payload(company.id, row) for row in self.lead_intake.list(company.id)]
        open_rows = [row for row in rows if row["status"] not in {"CONVERTED", "DISMISSED"}]
        by_status: dict[str, int] = {}
        by_connector: dict[str, int] = {}
        for row in rows:
            by_status[row["status"]] = by_status.get(row["status"], 0) + 1
            by_connector[row["connector"]] = by_connector.get(row["connector"], 0) + 1
        identifiable = sum(1 for row in rows if row["identity_keys_present"])
        converted = sum(1 for row in rows if row["converted_contact_id"])
        attributed = sum(1 for row in rows if row["attribution_verified"])
        duplicate_pairs = sum(row["duplicate_open_lead_count"] for row in open_rows) // 2
        total = len(rows)
        return {
            "schema": "binario.marketing.lead-intake-center.v1",
            "company_id": company.id,
            "summary": {
                "total": total,
                "open": len(open_rows),
                "new": by_status.get("NEW", 0),
                "matched": by_status.get("MATCHED", 0),
                "conflict": by_status.get("CONFLICT", 0),
                "unidentified": by_status.get("UNIDENTIFIED", 0),
                "converted": by_status.get("CONVERTED", 0),
                "dismissed": by_status.get("DISMISSED", 0),
                "attributed": attributed,
                "open_duplicate_pairs": duplicate_pairs,
                "identity_coverage_percent": round(identifiable * 100 / total, 2) if total else 0.0,
                "conversion_percent": round(converted * 100 / total, 2) if total else 0.0,
                "by_connector": by_connector,
            },
            "leads": rows[:500],
            "matching_contract": {
                "email": "EXACT_CASEFOLD",
                "phone_whatsapp": "EXACT_DIGITS",
                "instagram": "EXACT_HANDLE",
                "name_fuzzy_matching": False,
                "automatic_merge": False,
                "conflict_requires_user_selection": True,
            },
            "conversion_contract": {
                "intake_mutates_crm": False,
                "conversion_requires_explicit_post": True,
                "create_contact_blocked_when_exact_match_exists": True,
                "nonexact_contact_link_requires_confirmation": True,
                "opportunity_creation_explicit": True,
                "attribution_materialized_only_after_crm_reference_exists": True,
                "attribution_time": "ORIGINAL_LEAD_RECEIVED_AT",
            },
            "ingress_contract": {
                "local_api": True,
                "csv_import": True,
                "first_party_form_forwarding": True,
                "public_desktop_webhook": False,
                "browser_to_localhost_external_site": False,
                "supported_connectors": list(LEAD_CONNECTORS),
            },
            "safety": {
                "provider_call_performed": False,
                "provider_mutation_performed": False,
                "automatic_message_send": False,
                "automatic_campaign_action": False,
                "automatic_crm_conversion": False,
                "background_polling": False,
                "fuzzy_identity_guessing": False,
            },
        }

    def lead_detail(self, company_id: str, lead_id: str) -> dict:
        company = self.companies.get(company_id)
        return self._lead_payload(company.id, self.lead_intake.get(company.id, lead_id))

    def intake_lead(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("lead intake payload must be an object")
        _assert_secret_free(payload)
        company = self.companies.get(company_id)
        allowed = {"connector", "source_ref", "attribution_capture", *_CONTACT_INPUT_FIELDS}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported lead intake fields: {', '.join(sorted(unknown))}")
        connector = str(payload.get("connector") or "API_IMPORT").strip().upper()
        if connector not in LEAD_CONNECTORS:
            raise ValueError(f"connector must be one of {', '.join(LEAD_CONNECTORS)}")
        values = {key: value for key, value in payload.items() if key in _CONTACT_INPUT_FIELDS}
        values["connector"] = connector
        if payload.get("source_ref") not in (None, ""):
            values["source_ref"] = payload.get("source_ref")
        prepared = self._prepare_first_party_capture(company.id, payload.get("attribution_capture"))
        if prepared:
            for key in (
                "tracking_link_id", "tracking_code", "utm_source", "utm_medium",
                "utm_campaign", "utm_id", "utm_content", "utm_term", "utm_source_platform",
            ):
                values[key] = prepared.get(key)
        values["received_at"] = _now()

        source_ref = str(values.get("source_ref") or "").strip() or None
        before_id = None
        if source_ref:
            for current in self.lead_intake.list(company.id):
                if current.connector == connector and current.source_ref == source_ref:
                    before_id = current.id
                    break
        row = self.lead_intake.create(company.id, values)
        reused = before_id == row.id if before_id else False
        if not reused:
            self.workspace.registries.timeline.append("lead.intake.received", {
                "company_id": company.id,
                "lead_id": row.id,
                "connector": row.connector,
                "has_exact_identity": bool(identity_keys(asdict(row))),
                "attribution_verified": bool(row.tracking_code),
                "crm_mutation_performed": False,
                "provider_mutation_performed": False,
            })
        result = self._lead_payload(company.id, row)
        result["idempotent_reuse"] = reused
        return result

    def import_leads_csv(self, company_id: str, content: bytes) -> dict:
        company = self.companies.get(company_id)
        rows, parse_errors = parse_lead_csv(content)
        digest = hashlib.sha256(bytes(content)).hexdigest()
        created = 0
        reused = 0
        errors = list(parse_errors)
        lead_ids: list[str] = []
        for row_number, payload in rows:
            values = dict(payload)
            values["connector"] = "CSV_IMPORT"
            values["source_ref"] = str(values.get("source_ref") or f"sha256:{digest}:row:{row_number}")
            try:
                result = self.intake_lead(company.id, values)
                lead_ids.append(result["id"])
                if result.get("idempotent_reuse"):
                    reused += 1
                else:
                    created += 1
            except (ValueError, TypeError, KeyError) as exc:
                errors.append({"row": row_number, "error": str(exc)})
            if len(errors) >= 100:
                errors = errors[:100]
                break
        report = {
            "schema": "binario.marketing.lead-intake-csv-report.v1",
            "rows": len(rows) + len(parse_errors),
            "created": created,
            "reused": reused,
            "errors": errors,
            "error_count": len(errors),
            "lead_ids": list(dict.fromkeys(lead_ids)),
            "crm_mutations": 0,
            "provider_mutations": 0,
            "source_sha256": digest,
        }
        self.workspace.registries.timeline.append("lead.intake.csv_imported", {
            "company_id": company.id,
            "rows": report["rows"],
            "created": created,
            "reused": reused,
            "error_count": report["error_count"],
            "crm_mutations": 0,
            "provider_mutations": 0,
        })
        return report

    def _lead_attribution_prepared(self, company_id: str, lead) -> dict | None:
        if not lead.tracking_code:
            return None
        company = self.companies.get(company_id)
        link = self.attribution.get_link_by_code(company.id, lead.tracking_code)
        if link.id != lead.tracking_link_id:
            raise ValueError("lead attribution link identity no longer matches canonical tracking link")
        for field in (
            "utm_source", "utm_medium", "utm_campaign", "utm_id",
            "utm_content", "utm_term", "utm_source_platform",
        ):
            if getattr(lead, field) != getattr(link, field):
                raise ValueError(f"lead {field} no longer matches canonical tracking link")
        return {
            "tracking_link_id": link.id,
            "tracking_code": link.tracking_code,
            "utm_source": link.utm_source,
            "utm_medium": link.utm_medium,
            "utm_campaign": link.utm_campaign,
            "utm_id": link.utm_id,
            "utm_content": link.utm_content,
            "utm_term": link.utm_term,
            "utm_source_platform": link.utm_source_platform,
            "landing_url": None,
            "referrer_url": None,
            "bridge_version": None,
            "client_captured_at": None,
        }

    def _materialize_lead_attribution(
        self,
        company_id: str,
        lead,
        *,
        contact_id: str | None,
        opportunity_id: str | None,
    ) -> dict | None:
        prepared = self._lead_attribution_prepared(company_id, lead)
        if not prepared:
            return None
        company = self.companies.get(company_id)
        record = self.first_party_captures.create(company.id, {
            **prepared,
            "contact_id": contact_id,
            "opportunity_id": opportunity_id,
            "source": "API_IMPORT",
            "received_at": lead.received_at,
        })
        claim = self.record_attribution_claim(company.id, {
            "tracking_code": record.tracking_code,
            "contact_id": record.contact_id,
            "opportunity_id": record.opportunity_id,
            "captured_at": lead.received_at,
        })
        self.workspace.registries.timeline.append("lead.intake.attribution_materialized", {
            "company_id": company.id,
            "lead_id": lead.id,
            "capture_id": record.id,
            "attribution_claim_id": claim["id"],
            "connector": lead.connector,
            "attribution_time": lead.received_at,
            "conversion_time_used_for_credit": False,
            "provider_mutation_performed": False,
        })
        return {"capture": asdict(record), "claim": claim}

    @staticmethod
    def _new_contact_payload(lead) -> dict:
        if not lead.name:
            raise ValueError("creating a new CRM contact requires lead name")
        payload = {}
        for field in _CONTACT_INPUT_FIELDS:
            value = getattr(lead, field)
            if field == "tags":
                if value:
                    payload[field] = list(value)
            elif value not in (None, ""):
                payload[field] = value
        return payload

    def convert_lead(self, company_id: str, lead_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("lead conversion payload must be an object")
        _assert_secret_free(payload)
        allowed = {"action", "contact_id", "confirm_user_selected", "opportunity"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported lead conversion fields: {', '.join(sorted(unknown))}")
        company = self.companies.get(company_id)
        lead = self.lead_intake.get(company.id, lead_id)
        if lead.dismissed_at:
            raise ValueError("dismissed lead cannot be converted")
        action = str(payload.get("action") or "").strip().upper()
        if action not in {"CREATE_CONTACT", "LINK_CONTACT"}:
            if not lead.converted_contact_id:
                raise ValueError("action must be CREATE_CONTACT or LINK_CONTACT")
            action = "LINK_CONTACT"

        matches = self._lead_exact_matches(company.id, lead)
        exact_ids = {row.id for row in matches}
        contact = None
        basis = lead.conversion_basis

        if lead.converted_contact_id:
            contact = self.crm.get_contact(lead.converted_contact_id)
            if contact.company_id != company.id:
                raise KeyError(lead.converted_contact_id)
        elif action == "CREATE_CONTACT":
            if matches:
                raise ValueError("exact CRM identity match exists; link or resolve the conflict instead of creating a duplicate")
            contact_payload = self._new_contact_payload(lead)
            contact_result = super().create_contact(company.id, contact_payload)
            contact = self.crm.get_contact(contact_result["id"])
            basis = "CREATED_NEW_CONTACT"
            lead = self.lead_intake.mark_contact_conversion(company.id, lead.id, contact.id, basis=basis)
            self._materialize_lead_attribution(company.id, lead, contact_id=contact.id, opportunity_id=None)
        else:
            contact_id = str(payload.get("contact_id") or "").strip()
            if not contact_id:
                if len(matches) == 1:
                    contact_id = matches[0].id
                else:
                    raise ValueError("LINK_CONTACT requires contact_id when there is not exactly one exact match")
            contact = self.crm.get_contact(contact_id)
            if contact.company_id != company.id:
                raise KeyError(contact_id)
            if contact.id in exact_ids:
                basis = "EXACT_IDENTITY_MATCH"
            elif not bool(payload.get("confirm_user_selected")):
                raise ValueError("linking a nonexact contact requires confirm_user_selected=true")
            else:
                basis = "USER_SELECTED_CONTACT"
            lead = self.lead_intake.mark_contact_conversion(company.id, lead.id, contact.id, basis=basis)
            self._materialize_lead_attribution(company.id, lead, contact_id=contact.id, opportunity_id=None)

        opportunity = None
        opportunity_payload = payload.get("opportunity")
        if opportunity_payload is not None:
            if not isinstance(opportunity_payload, dict):
                raise ValueError("opportunity must be an object")
            unknown_opp = set(opportunity_payload) - _OPPORTUNITY_INPUT_FIELDS
            if unknown_opp:
                raise ValueError(f"unsupported opportunity fields: {', '.join(sorted(unknown_opp))}")
            if lead.converted_opportunity_id:
                opportunity = self.crm.get_opportunity(lead.converted_opportunity_id)
                if opportunity.company_id != company.id:
                    raise KeyError(lead.converted_opportunity_id)
            else:
                values = dict(opportunity_payload)
                values["contact_id"] = contact.id
                opportunity_result = super().create_opportunity(company.id, values)
                opportunity = self.crm.get_opportunity(opportunity_result["id"])
                lead = self.lead_intake.mark_opportunity_conversion(company.id, lead.id, opportunity.id)
                self._materialize_lead_attribution(
                    company.id,
                    lead,
                    contact_id=contact.id,
                    opportunity_id=opportunity.id,
                )

        self.workspace.registries.timeline.append("lead.intake.converted", {
            "company_id": company.id,
            "lead_id": lead.id,
            "connector": lead.connector,
            "contact_id": contact.id,
            "opportunity_id": opportunity.id if opportunity else lead.converted_opportunity_id,
            "conversion_basis": basis,
            "explicit_user_action": True,
            "provider_mutation_performed": False,
            "external_message_sent": False,
        })
        result = self._lead_payload(company.id, self.lead_intake.get(company.id, lead.id))
        result["contact"] = asdict(contact)
        result["opportunity"] = asdict(opportunity) if opportunity else None
        return result

    def dismiss_lead(self, company_id: str, lead_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("lead dismissal payload must be an object")
        if set(payload) - {"reason"}:
            raise ValueError("unsupported lead dismissal fields")
        company = self.companies.get(company_id)
        row = self.lead_intake.dismiss(company.id, lead_id, payload.get("reason"))
        self.workspace.registries.timeline.append("lead.intake.dismissed", {
            "company_id": company.id,
            "lead_id": row.id,
            "connector": row.connector,
            "explicit_user_action": True,
            "crm_mutation_performed": False,
            "provider_mutation_performed": False,
        })
        return self._lead_payload(company.id, row)

    def learning_payload(self, company_id: str) -> dict:
        payload = super().learning_payload(company_id)
        intake = self.lead_intake_payload(company_id)
        payload.setdefault("attribution", {})["lead_intake"] = {
            "total": intake["summary"]["total"],
            "open": intake["summary"]["open"],
            "converted": intake["summary"]["converted"],
            "attributed": intake["summary"]["attributed"],
            "identity_coverage_percent": intake["summary"]["identity_coverage_percent"],
            "conversion_percent": intake["summary"]["conversion_percent"],
        }
        return payload

    def _ai_context(self, company_id: str, *, task: str, campaign_id: str | None, creative_media_id: str | None) -> dict:
        context = super()._ai_context(
            company_id,
            task=task,
            campaign_id=campaign_id,
            creative_media_id=creative_media_id,
        )
        intake = self.lead_intake_payload(company_id)
        context["lead_intake"] = {
            "summary": intake["summary"],
            "connectors": intake["summary"]["by_connector"],
            "matching": {
                "fuzzy_name_matching": False,
                "automatic_merge": False,
                "exact_identity_only": True,
            },
            "privacy": {
                "lead_rows_included": False,
                "contact_pii_included": False,
                "lead_ids_included": False,
                "tracking_codes_included": False,
            },
        }
        return context


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/lead-intake.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "lead-intake":
                self._json(self.server.runtime.lead_intake_payload(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "lead-intake":
                self._json(self.server.runtime.lead_detail(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "lead-intake":
                with self.server.mutation_lock:
                    result = self.server.runtime.intake_lead(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["lead-intake", "csv"]:
                raw_length = self.headers.get("Content-Length")
                if raw_length is None:
                    raise ValueError("Content-Length is required for lead CSV intake")
                try:
                    length = int(raw_length)
                except ValueError as exc:
                    raise ValueError("invalid Content-Length") from exc
                if length <= 0 or length > MAX_LEAD_CSV_BYTES:
                    raise ValueError("lead CSV intake must be between 1 byte and 10 MiB")
                content = self.rfile.read(length)
                if len(content) != length:
                    raise ValueError("CSV body ended before Content-Length")
                with self.server.mutation_lock:
                    result = self.server.runtime.import_leads_csv(parts[2], content)
                self._json(result, HTTPStatus.CREATED)
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "lead-intake"
                and parts[5] == "convert"
            ):
                with self.server.mutation_lock:
                    result = self.server.runtime.convert_lead(parts[2], parts[4], self._body())
                self._json(result)
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "lead-intake"
                and parts[5] == "dismiss"
            ):
                with self.server.mutation_lock:
                    result = self.server.runtime.dismiss_lead(parts[2], parts[4], self._body())
                self._json(result)
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
