from __future__ import annotations

import secrets
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlparse

from .public_gateway import (
    GatewayCredentialStore,
    PublicGatewayClient,
    PublicGatewayConfigStore,
    derive_tenant_secret,
    verify_envelope,
)
from .social_store import _assert_secret_free
from . import service_wave55_guard_app as base


_GATEWAY_CONTACT_FIELDS = {
    "name", "organization", "role", "email", "phone", "whatsapp",
    "instagram", "source", "tags", "notes",
}


class AppRuntime(base.AppRuntime):
    """Wave 56 adds explicit signed public-gateway sync without background polling."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.public_gateway_configs = PublicGatewayConfigStore(runtime.data_root / "State" / "public-gateway")
        runtime.public_gateway_credentials = GatewayCredentialStore()
        return runtime

    def gateway_credential_payload(self) -> dict:
        status = self.public_gateway_credentials.status()
        return {
            "schema": "binario.marketing.public-gateway-credential-status.v1",
            "configured": status.configured,
            "source": status.source,
            "writable": status.writable,
            "secret_returned": False,
        }

    def set_gateway_credential(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("gateway credential payload must be an object")
        unknown = set(payload) - {"master_secret", "generate_and_reveal"}
        if unknown:
            raise ValueError(f"unsupported gateway credential fields: {', '.join(sorted(unknown))}")
        generated = bool(payload.get("generate_and_reveal"))
        supplied = str(payload.get("master_secret") or "").strip()
        if generated and supplied:
            raise ValueError("choose either master_secret or generate_and_reveal")
        secret = secrets.token_urlsafe(48) if generated else supplied
        if not secret:
            raise ValueError("gateway master secret is required")
        status = self.public_gateway_credentials.write(secret)
        result = {
            "schema": "binario.marketing.public-gateway-credential-status.v1",
            "configured": status.configured,
            "source": status.source,
            "writable": status.writable,
            "secret_returned": generated,
        }
        if generated:
            result["generated_master_secret"] = secret
        self.workspace.registries.timeline.append("public.gateway.credential_configured", {
            "configured": True,
            "source": status.source,
            "secret_logged": False,
        })
        return result

    def delete_gateway_credential(self) -> dict:
        status = self.public_gateway_credentials.delete()
        self.workspace.registries.timeline.append("public.gateway.credential_removed", {
            "configured": status.configured,
            "secret_logged": False,
        })
        return {
            "schema": "binario.marketing.public-gateway-credential-status.v1",
            "configured": status.configured,
            "source": status.source,
            "writable": status.writable,
            "secret_returned": False,
        }

    def public_gateway_payload(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        config = self.public_gateway_configs.get(company.id)
        credential = self.gateway_credential_payload()
        return {
            "schema": "binario.marketing.public-gateway-center.v1",
            "company_id": company.id,
            "config": asdict(config) if config else None,
            "credential": credential,
            "readiness": {
                "gateway_url_configured": bool(config),
                "tenant_configured": bool(config),
                "master_secret_configured": bool(credential["configured"]),
                "ready_to_sync": bool(config and credential["configured"]),
            },
            "protocol": {
                "ingress": "HMAC_SHA256_V1",
                "pull": "HMAC_SHA256_V1",
                "timestamp_window_seconds": 300,
                "event_idempotency": "TENANT_PLUS_EVENT_ID",
                "remote_retention_days": 30,
                "ack_redacts_remote_payload": True,
                "site_secret_is_tenant_derived": True,
                "browser_secret_supported": False,
            },
            "safety": {
                "sync_requires_explicit_post": True,
                "background_polling": False,
                "gateway_can_mutate_crm": False,
                "gateway_can_call_marketing_providers": False,
                "local_intake_precedes_remote_ack": True,
                "failed_local_intake_is_not_acked": True,
                "master_secret_persisted_in_json": False,
                "pull_secret_exposed_to_browser": False,
            },
        }

    def configure_public_gateway(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        row = self.public_gateway_configs.upsert(company.id, payload)
        self.workspace.registries.timeline.append("public.gateway.configured", {
            "company_id": company.id,
            "tenant_id": row.tenant_id,
            "gateway_origin": row.gateway_url,
            "secret_logged": False,
        })
        return self.public_gateway_payload(company.id)

    def reveal_gateway_site_secret(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        config = self.public_gateway_configs.get(company.id)
        if not config:
            raise ValueError("public gateway must be configured first")
        master = self.public_gateway_credentials.read()
        if not master:
            raise ValueError("gateway master secret is not configured")
        secret = derive_tenant_secret(master, config.tenant_id, purpose="ingress")
        return {
            "schema": "binario.marketing.public-gateway-site-secret.v1",
            "tenant_id": config.tenant_id,
            "site_secret": secret,
            "purpose": "SERVER_TO_SERVER_INGRESS_ONLY",
            "browser_safe": False,
            "persisted_in_company_json": False,
        }

    def _gateway_client(self, company_id: str) -> PublicGatewayClient:
        company = self.companies.get(company_id)
        config = self.public_gateway_configs.get(company.id)
        if not config:
            raise ValueError("public gateway must be configured first")
        master = self.public_gateway_credentials.read()
        if not master:
            raise ValueError("gateway master secret is not configured")
        pull_secret = derive_tenant_secret(master, config.tenant_id, purpose="pull")
        return PublicGatewayClient(config.gateway_url, config.tenant_id, pull_secret)

    def _intake_gateway_envelope(self, company_id: str, envelope: dict, *, pull_secret: str, tenant_id: str) -> dict:
        company = self.companies.get(company_id)
        public_payload = verify_envelope(envelope, tenant_id=tenant_id, pull_secret=pull_secret)
        lead = public_payload.get("lead")
        if not isinstance(lead, dict):
            raise ValueError("gateway lead must be an object")
        _assert_secret_free(lead)
        allowed = {*_GATEWAY_CONTACT_FIELDS, "attribution_capture"}
        unknown = set(lead) - allowed
        if unknown:
            raise ValueError(f"unsupported gateway lead fields: {', '.join(sorted(unknown))}")
        values = {key: value for key, value in lead.items() if key in _GATEWAY_CONTACT_FIELDS}
        values["connector"] = "API_IMPORT"
        values["source_ref"] = f"public_gateway:{tenant_id}:{envelope['event_id']}"
        if not values.get("source"):
            values["source"] = "public_gateway"
        prepared = self._prepare_first_party_capture(company.id, lead.get("attribution_capture"))
        if prepared:
            for key in (
                "tracking_link_id", "tracking_code", "utm_source", "utm_medium", "utm_campaign",
                "utm_id", "utm_content", "utm_term", "utm_source_platform",
            ):
                values[key] = prepared.get(key)
        values["received_at"] = str(envelope.get("received_at") or "")
        before = None
        for current in self.lead_intake.list(company.id):
            if current.connector == "API_IMPORT" and current.source_ref == values["source_ref"]:
                before = current.id
                break
        row = self.lead_intake.create(company.id, values)
        reused = before == row.id if before else False
        if not reused:
            self.workspace.registries.timeline.append("public.gateway.lead_received", {
                "company_id": company.id,
                "lead_id": row.id,
                "tenant_id": tenant_id,
                "event_id": envelope["event_id"],
                "gateway_received_at": envelope["received_at"],
                "crm_mutation_performed": False,
                "provider_mutation_performed": False,
            })
        result = self._lead_payload(company.id, row)
        result["gateway_event_id"] = envelope["event_id"]
        result["idempotent_reuse"] = reused
        return result

    def sync_public_gateway(self, company_id: str, payload: dict | None = None) -> dict:
        company = self.companies.get(company_id)
        body = payload or {}
        if not isinstance(body, dict) or set(body) - {"limit"}:
            raise ValueError("gateway sync payload only supports limit")
        limit = max(1, min(int(body.get("limit", 50)), 100))
        config = self.public_gateway_configs.get(company.id)
        if not config:
            raise ValueError("public gateway must be configured first")
        master = self.public_gateway_credentials.read()
        if not master:
            raise ValueError("gateway master secret is not configured")
        pull_secret = derive_tenant_secret(master, config.tenant_id, purpose="pull")
        client = self._gateway_client(company.id)
        envelopes = client.pull(limit=limit)
        imported = []
        errors = []
        ack_ids = []
        for envelope in envelopes:
            event_id = str(envelope.get("event_id") or "") if isinstance(envelope, dict) else ""
            try:
                lead = self._intake_gateway_envelope(
                    company.id, envelope, pull_secret=pull_secret, tenant_id=config.tenant_id,
                )
                imported.append({
                    "event_id": event_id,
                    "lead_id": lead["id"],
                    "idempotent_reuse": bool(lead.get("idempotent_reuse")),
                    "attribution_verified": bool(lead.get("attribution_verified")),
                })
                ack_ids.append(event_id)
            except Exception as exc:
                errors.append({"event_id": event_id or None, "error": str(exc)})
        ack = {"requested": 0, "acked": 0}
        ack_error = None
        if ack_ids:
            try:
                ack = client.ack(ack_ids)
            except Exception as exc:
                ack_error = str(exc)
        result = {
            "schema": "binario.marketing.public-gateway-sync.v1",
            "company_id": company.id,
            "tenant_id": config.tenant_id,
            "pulled": len(envelopes),
            "imported": len(imported),
            "failed": len(errors),
            "ack_requested": len(ack_ids),
            "ack_confirmed": int(ack.get("acked", 0)) if isinstance(ack, dict) else 0,
            "ack_error": ack_error,
            "results": imported,
            "errors": errors,
            "crm_mutations": 0,
            "provider_mutations": 0,
            "background_polling": False,
        }
        self.workspace.registries.timeline.append("public.gateway.sync", {
            "company_id": company.id,
            "tenant_id": config.tenant_id,
            "pulled": result["pulled"],
            "imported": result["imported"],
            "failed": result["failed"],
            "ack_confirmed": result["ack_confirmed"],
            "crm_mutations": 0,
            "provider_mutations": 0,
            "explicit_user_action": True,
        })
        return result

    def learning_payload(self, company_id: str) -> dict:
        payload = super().learning_payload(company_id)
        center = self.public_gateway_payload(company_id)
        payload.setdefault("attribution", {})["public_gateway"] = {
            "configured": center["readiness"]["gateway_url_configured"],
            "ready_to_sync": center["readiness"]["ready_to_sync"],
            "background_polling": False,
        }
        return payload

    def _ai_context(self, company_id: str, *, task: str, campaign_id: str | None, creative_media_id: str | None) -> dict:
        context = super()._ai_context(company_id, task=task, campaign_id=campaign_id, creative_media_id=creative_media_id)
        center = self.public_gateway_payload(company_id)
        context["public_gateway"] = {
            "configured": center["readiness"]["gateway_url_configured"],
            "ready_to_sync": center["readiness"]["ready_to_sync"],
            "protocol": "HMAC_SHA256_V1",
            "privacy": {
                "gateway_url_included": False,
                "tenant_id_included": False,
                "master_secret_included": False,
                "site_secret_included": False,
                "lead_payloads_included": False,
            },
        }
        return context


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/public-gateway.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "public-gateway":
                self._json(self.server.runtime.public_gateway_payload(parts[2]))
                return
            if parts == ["api", "public-gateway", "credential"]:
                self._json(self.server.runtime.gateway_credential_payload())
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if parts == ["api", "public-gateway", "credential"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.set_gateway_credential(self._body())
                self._json(result)
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["public-gateway", "config"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.configure_public_gateway(parts[2], self._body())
                self._json(result)
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["public-gateway", "site-secret"]:
                self._json(self.server.runtime.reveal_gateway_site_secret(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["public-gateway", "sync"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.sync_public_gateway(parts[2], self._body())
                self._json(result)
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        parts = self._segments()
        try:
            if parts == ["api", "public-gateway", "credential"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.delete_gateway_credential()
                self._json(result)
                return
        except Exception as exc:
            self._wave51_error(exc)
            return
        super().do_DELETE()


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
