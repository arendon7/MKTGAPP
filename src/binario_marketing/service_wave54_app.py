from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse, urlsplit

from .capture_store import BRIDGE_VERSION_RE, FirstPartyCaptureStore
from .social_store import _assert_secret_free, _now
from . import service_wave53_app as base


_CAPTURE_UTM_FIELDS = (
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_id",
    "utm_content",
    "utm_term",
    "utm_source_platform",
)
_CAPTURE_INPUT_FIELDS = {
    "bm_tid",
    "tracking_code",
    *_CAPTURE_UTM_FIELDS,
    "landing_url",
    "referrer_url",
    "bridge_version",
    "client_captured_at",
}


def _capture_http_url(value: object, *, field: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    if len(raw) > 3000:
        raise ValueError(f"{field} is too long")
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{field} must not contain embedded credentials")
    return raw


def _capture_client_time(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("client_captured_at must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError("client_captured_at must include timezone")
    return parsed.isoformat()


class AppRuntime(base.AppRuntime):
    """Wave 54 transports first-party tracking evidence into CRM without attribution guessing."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.first_party_captures = FirstPartyCaptureStore(runtime.data_root / "State" / "first-party-captures")
        return runtime

    def _prepare_first_party_capture(self, company_id: str, payload: dict | None) -> dict | None:
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise ValueError("attribution_capture must be an object")
        _assert_secret_free(payload)
        unknown = set(payload) - _CAPTURE_INPUT_FIELDS
        if unknown:
            raise ValueError(f"unsupported attribution_capture fields: {', '.join(sorted(unknown))}")
        company = self.companies.get(company_id)
        code_a = str(payload.get("bm_tid") or "").strip()
        code_b = str(payload.get("tracking_code") or "").strip()
        if code_a and code_b and code_a != code_b:
            raise ValueError("bm_tid and tracking_code disagree")
        code = code_a or code_b
        if not code:
            raise ValueError("attribution_capture requires bm_tid")
        link = self.attribution.get_link_by_code(company.id, code)

        for field in _CAPTURE_UTM_FIELDS:
            supplied = str(payload.get(field) or "").strip() or None
            canonical = getattr(link, field)
            if supplied is not None and supplied != canonical:
                raise ValueError(f"captured {field} does not match canonical tracking link")

        bridge_version = str(payload.get("bridge_version") or "").strip() or None
        if bridge_version and not BRIDGE_VERSION_RE.fullmatch(bridge_version):
            raise ValueError("invalid bridge_version")
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
            "landing_url": _capture_http_url(payload.get("landing_url"), field="landing_url"),
            "referrer_url": _capture_http_url(payload.get("referrer_url"), field="referrer_url"),
            "bridge_version": bridge_version,
            "client_captured_at": _capture_client_time(payload.get("client_captured_at")),
        }

    def _record_prepared_capture(
        self,
        company_id: str,
        prepared: dict,
        *,
        contact_id: str | None,
        opportunity_id: str | None,
        source: str,
    ) -> dict:
        company = self.companies.get(company_id)
        if contact_id:
            contact = self.crm.get_contact(contact_id)
            if contact.company_id != company.id:
                raise KeyError(contact_id)
        if opportunity_id:
            opportunity = self.crm.get_opportunity(opportunity_id)
            if opportunity.company_id != company.id:
                raise KeyError(opportunity_id)
            if opportunity.contact_id and contact_id and opportunity.contact_id != contact_id:
                raise ValueError("capture contact does not match opportunity")
            if not contact_id and opportunity.contact_id:
                contact_id = opportunity.contact_id
        received_at = _now()
        record = self.first_party_captures.create(company.id, {
            **prepared,
            "contact_id": contact_id,
            "opportunity_id": opportunity_id,
            "source": source,
            "received_at": received_at,
        })
        claim = self.record_attribution_claim(company.id, {
            "tracking_code": record.tracking_code,
            "contact_id": record.contact_id,
            "opportunity_id": record.opportunity_id,
            "captured_at": record.received_at,
        })
        self.workspace.registries.timeline.append("attribution.first_party_capture.recorded", {
            "company_id": company.id,
            "capture_id": record.id,
            "attribution_claim_id": claim["id"],
            "tracking_link_id": record.tracking_link_id,
            "source": record.source,
            "contact_linked": bool(record.contact_id),
            "opportunity_linked": bool(record.opportunity_id),
            "utm_validation": record.utm_validation,
            "browser_timestamp_authoritative": False,
            "provider_mutation_performed": False,
        })
        return {"capture": asdict(record), "claim": claim}

    def record_first_party_capture(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("first-party capture payload must be an object")
        allowed = _CAPTURE_INPUT_FIELDS | {"contact_id", "opportunity_id"}
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported first-party capture fields: {', '.join(sorted(unknown))}")
        prepared = self._prepare_first_party_capture(company_id, {key: value for key, value in payload.items() if key in _CAPTURE_INPUT_FIELDS})
        assert prepared is not None
        contact_id = str(payload.get("contact_id") or "").strip() or None
        opportunity_id = str(payload.get("opportunity_id") or "").strip() or None
        if not contact_id and not opportunity_id:
            raise ValueError("first-party capture requires contact_id or opportunity_id")
        return self._record_prepared_capture(
            company_id,
            prepared,
            contact_id=contact_id,
            opportunity_id=opportunity_id,
            source="API_IMPORT",
        )

    def create_contact(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("contact payload must be an object")
        values = dict(payload)
        prepared = self._prepare_first_party_capture(company_id, values.pop("attribution_capture", None))
        result = super().create_contact(company_id, values)
        if prepared:
            self._record_prepared_capture(
                company_id,
                prepared,
                contact_id=result["id"],
                opportunity_id=None,
                source="CRM_CONTACT_CREATE",
            )
        return result

    def update_contact(self, company_id: str, contact_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("contact payload must be an object")
        values = dict(payload)
        prepared = self._prepare_first_party_capture(company_id, values.pop("attribution_capture", None))
        result = super().update_contact(company_id, contact_id, values)
        if prepared:
            self._record_prepared_capture(
                company_id,
                prepared,
                contact_id=result["id"],
                opportunity_id=None,
                source="CRM_CONTACT_UPDATE",
            )
        return result

    def create_opportunity(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("opportunity payload must be an object")
        values = dict(payload)
        prepared = self._prepare_first_party_capture(company_id, values.pop("attribution_capture", None))
        result = super().create_opportunity(company_id, values)
        if prepared:
            self._record_prepared_capture(
                company_id,
                prepared,
                contact_id=result.get("contact_id"),
                opportunity_id=result["id"],
                source="CRM_OPPORTUNITY_CREATE",
            )
        return result

    def update_opportunity(self, company_id: str, opportunity_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("opportunity payload must be an object")
        values = dict(payload)
        prepared = self._prepare_first_party_capture(company_id, values.pop("attribution_capture", None))
        result = super().update_opportunity(company_id, opportunity_id, values)
        if prepared:
            self._record_prepared_capture(
                company_id,
                prepared,
                contact_id=result.get("contact_id"),
                opportunity_id=result["id"],
                source="CRM_OPPORTUNITY_UPDATE",
            )
        return result

    def capture_bridge_payload(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        captures = [asdict(row) for row in self.first_party_captures.list(company.id)]
        links = self.attribution.list_links(company.id)
        captured_link_ids = {row["tracking_link_id"] for row in captures}
        by_source: dict[str, int] = {}
        for row in captures:
            by_source[row["source"]] = by_source.get(row["source"], 0) + 1
        return {
            "schema": "binario.marketing.first-party-capture-bridge.v1",
            "company_id": company.id,
            "summary": {
                "capture_records": len(captures),
                "links_instrumented": len(links),
                "links_with_capture": len(captured_link_ids),
                "contact_captures": sum(1 for row in captures if row["contact_id"]),
                "opportunity_captures": sum(1 for row in captures if row["opportunity_id"]),
                "by_source": by_source,
            },
            "captures": captures[:100],
            "form_contract": {
                "hidden_fields": ["bm_tid", *_CAPTURE_UTM_FIELDS, "bm_client_captured_at", "bm_landing_url", "bm_referrer_url", "bm_bridge_version"],
                "crm_json_field": "attribution_capture",
                "portable_script": "/first-party-capture-bridge.js",
                "storage": "sessionStorage",
                "network_calls": False,
                "automatic_submit": False,
            },
            "evidence_contract": {
                "canonical_resolution": "bm_tid -> immutable tracking link",
                "utm_mismatch": "REJECT",
                "server_received_at_authoritative": True,
                "client_timestamp_authoritative": False,
                "full_form_body_persisted": False,
                "contact_pii_persisted_in_capture_store": False,
                "landing_query_persisted": False,
                "referrer_query_persisted": False,
            },
            "safety": {
                "provider_call_performed": False,
                "provider_mutation_performed": False,
                "background_polling": False,
                "clicks_observed": False,
                "temporal_inference": False,
                "automatic_form_submit": False,
            },
        }

    def attribution_payload(self, company_id: str) -> dict:
        payload = super().attribution_payload(company_id)
        bridge = self.capture_bridge_payload(company_id)
        payload["capture_bridge"] = {
            "schema": bridge["schema"],
            "summary": bridge["summary"],
            "server_received_at_authoritative": True,
            "utm_mismatch": "REJECT",
        }
        return payload

    def learning_payload(self, company_id: str) -> dict:
        payload = super().learning_payload(company_id)
        bridge = self.capture_bridge_payload(company_id)
        payload["attribution"]["first_party_capture_records"] = bridge["summary"]["capture_records"]
        payload["attribution"]["links_with_first_party_capture"] = bridge["summary"]["links_with_capture"]
        payload["attribution"]["capture_bridge_network_calls"] = False
        return payload

    def _ai_context(self, company_id: str, *, task: str, campaign_id: str | None, creative_media_id: str | None) -> dict:
        context = super()._ai_context(company_id, task=task, campaign_id=campaign_id, creative_media_id=creative_media_id)
        bridge = self.capture_bridge_payload(company_id)
        context.setdefault("attribution", {})["first_party_capture_bridge"] = {
            "capture_records": bridge["summary"]["capture_records"],
            "links_instrumented": bridge["summary"]["links_instrumented"],
            "links_with_capture": bridge["summary"]["links_with_capture"],
            "contact_captures": bridge["summary"]["contact_captures"],
            "opportunity_captures": bridge["summary"]["opportunity_captures"],
            "server_received_at_authoritative": True,
            "contact_pii_included": False,
            "tracking_codes_included": False,
            "landing_or_referrer_hosts_included": False,
        }
        return context


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/capture-bridge.js", "/first-party-capture-bridge.js"}:
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["attribution", "capture-bridge"]:
                self._json(self.server.runtime.capture_bridge_payload(parts[2]))
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["attribution", "captures"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.record_first_party_capture(parts[2], self._body())
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
