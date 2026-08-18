from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from .public_gateway_wave58 import (
    GatewayTenantAdminClient,
    GatewayTenantStateStore,
    VersionedPublicGatewayClient,
    derive_versioned_tenant_secret,
    verify_versioned_envelope,
)
from . import service_wave56_app as base


class AppRuntime(base.AppRuntime):
    """Wave 58 adds explicit tenant registration, independent rotation and revocation."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.gateway_tenant_states = GatewayTenantStateStore(runtime.data_root / "State" / "public-gateway-tenants")
        return runtime

    def public_gateway_payload(self, company_id: str) -> dict:
        payload = super().public_gateway_payload(company_id)
        state = self.gateway_tenant_states.get(company_id)
        active = bool(state and state.status == "ACTIVE")
        payload["tenant_registry"] = {
            "registered": state is not None,
            "status": state.status if state else "UNREGISTERED",
            "ingress_version": state.ingress_version if state else None,
            "pull_version": state.pull_version if state else None,
            "secret_values_included": False,
        }
        payload["readiness"]["tenant_registered"] = state is not None
        payload["readiness"]["tenant_active"] = active
        payload["readiness"]["ready_to_sync"] = bool(
            payload["readiness"]["gateway_url_configured"]
            and payload["readiness"]["master_secret_configured"]
            and active
        )
        payload["protocol"]["tenant_registry"] = "VERSIONED_V1"
        payload["protocol"]["independent_ingress_pull_rotation"] = True
        payload["protocol"]["credential_version_header"] = "X-Binario-Credential-Version"
        payload["safety"]["tenant_registration_is_explicit"] = True
        payload["safety"]["tenant_rotation_is_explicit"] = True
        payload["safety"]["tenant_revocation_is_explicit"] = True
        payload["safety"]["tenant_secret_persisted_in_registry"] = False
        return payload

    def gateway_tenant_action(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        config = self.public_gateway_configs.get(company.id)
        if not config:
            raise ValueError("public gateway must be configured first")
        if not isinstance(payload, dict) or set(payload) != {"action"}:
            raise ValueError("tenant control payload must contain only action")
        action = str(payload.get("action") or "").strip().upper()
        mapping = {
            "STATUS": ("STATUS", None),
            "REGISTER": ("REGISTER", None),
            "ROTATE_INGRESS": ("ROTATE", "ingress"),
            "ROTATE_PULL": ("ROTATE", "pull"),
            "REVOKE": ("REVOKE", None),
            "REACTIVATE": ("REACTIVATE", None),
        }
        if action not in mapping:
            raise ValueError("unsupported tenant control action")
        master = self.public_gateway_credentials.read()
        if not master:
            raise ValueError("gateway master secret is not configured")
        remote_action, purpose = mapping[action]
        client = GatewayTenantAdminClient(config.gateway_url, master)
        result = client.execute(config.tenant_id, remote_action, purpose=purpose)
        state = self.gateway_tenant_states.upsert_remote(company.id, result["tenant"])
        self.workspace.registries.timeline.append("public.gateway.tenant_control", {
            "company_id": company.id,
            "tenant_id": config.tenant_id,
            "action": action,
            "status": state.status,
            "ingress_version": state.ingress_version,
            "pull_version": state.pull_version,
            "explicit_user_action": True,
            "secret_logged": False,
            "crm_mutation_performed": False,
            "provider_mutation_performed": False,
        })
        return {
            "schema": "binario.marketing.gateway-tenant-control-result.v1",
            "action": action,
            "tenant": {
                "status": state.status,
                "ingress_version": state.ingress_version,
                "pull_version": state.pull_version,
            },
            "secret_returned": False,
            "center": self.public_gateway_payload(company.id),
        }

    def reveal_gateway_site_secret(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        config = self.public_gateway_configs.get(company.id)
        state = self.gateway_tenant_states.get(company.id)
        if not config:
            raise ValueError("public gateway must be configured first")
        if not state or state.tenant_id != config.tenant_id:
            raise ValueError("gateway tenant must be registered first")
        if state.status != "ACTIVE":
            raise ValueError("gateway tenant is revoked")
        master = self.public_gateway_credentials.read()
        if not master:
            raise ValueError("gateway master secret is not configured")
        secret = derive_versioned_tenant_secret(
            master, config.tenant_id, purpose="ingress", version=state.ingress_version,
        )
        return {
            "schema": "binario.marketing.public-gateway-site-secret.v2",
            "tenant_id": config.tenant_id,
            "credential_version": state.ingress_version,
            "site_secret": secret,
            "purpose": "SERVER_TO_SERVER_INGRESS_ONLY",
            "browser_safe": False,
            "persisted_in_company_json": False,
            "persisted_in_remote_registry": False,
        }

    def _gateway_client(self, company_id: str) -> VersionedPublicGatewayClient:
        company = self.companies.get(company_id)
        config = self.public_gateway_configs.get(company.id)
        state = self.gateway_tenant_states.get(company.id)
        if not config:
            raise ValueError("public gateway must be configured first")
        if not state or state.tenant_id != config.tenant_id:
            raise ValueError("gateway tenant must be registered first")
        if state.status != "ACTIVE":
            raise ValueError("gateway tenant is revoked")
        master = self.public_gateway_credentials.read()
        if not master:
            raise ValueError("gateway master secret is not configured")
        pull_secret = derive_versioned_tenant_secret(
            master, config.tenant_id, purpose="pull", version=state.pull_version,
        )
        return VersionedPublicGatewayClient(
            config.gateway_url,
            config.tenant_id,
            pull_secret,
            pull_version=state.pull_version,
        )

    def _intake_gateway_envelope(self, company_id: str, envelope: dict, *, pull_secret: str, tenant_id: str, pull_version: int = 1) -> dict:
        verify_versioned_envelope(
            envelope,
            tenant_id=tenant_id,
            pull_secret=pull_secret,
            pull_version=pull_version,
        )
        legacy = dict(envelope)
        legacy.pop("credential_version", None)
        return super()._intake_gateway_envelope(
            company_id,
            legacy,
            pull_secret=pull_secret,
            tenant_id=tenant_id,
        )

    def sync_public_gateway(self, company_id: str, payload: dict | None = None) -> dict:
        company = self.companies.get(company_id)
        body = payload or {}
        if not isinstance(body, dict) or set(body) - {"limit"}:
            raise ValueError("gateway sync payload only supports limit")
        limit = max(1, min(int(body.get("limit", 50)), 100))
        config = self.public_gateway_configs.get(company.id)
        state = self.gateway_tenant_states.get(company.id)
        if not config:
            raise ValueError("public gateway must be configured first")
        if not state or state.tenant_id != config.tenant_id:
            raise ValueError("gateway tenant must be registered first")
        if state.status != "ACTIVE":
            raise ValueError("gateway tenant is revoked")
        master = self.public_gateway_credentials.read()
        if not master:
            raise ValueError("gateway master secret is not configured")
        pull_secret = derive_versioned_tenant_secret(
            master, config.tenant_id, purpose="pull", version=state.pull_version,
        )
        client = self._gateway_client(company.id)
        envelopes = client.pull(limit=limit)
        imported = []
        errors = []
        ack_ids = []
        for envelope in envelopes:
            event_id = str(envelope.get("event_id") or "") if isinstance(envelope, dict) else ""
            try:
                lead = self._intake_gateway_envelope(
                    company.id,
                    envelope,
                    pull_secret=pull_secret,
                    tenant_id=config.tenant_id,
                    pull_version=state.pull_version,
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
            "schema": "binario.marketing.public-gateway-sync.v2",
            "company_id": company.id,
            "tenant_id": config.tenant_id,
            "pull_version": state.pull_version,
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
            "pull_version": state.pull_version,
            "pulled": result["pulled"],
            "imported": result["imported"],
            "failed": result["failed"],
            "ack_confirmed": result["ack_confirmed"],
            "crm_mutations": 0,
            "provider_mutations": 0,
            "explicit_user_action": True,
        })
        return result


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/public-gateway-wave58.js":
            self._static(path)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["public-gateway", "tenant-control"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.gateway_tenant_action(parts[2], self._body())
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
