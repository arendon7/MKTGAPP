from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave74_app as base
from .uat_sandbox_store import UATSandboxStore


class AppRuntime(base.AppRuntime):
    """Wave 75 creates explicit synthetic functional-UAT data isolated from release evidence."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.uat_sandbox = UATSandboxStore(runtime.data_root / "State" / "uat-sandbox")
        return runtime

    def _sandbox_company(self, manifest: dict | None):
        if not manifest:
            return None
        try:
            return self.companies.get(str(manifest.get("company_id") or ""))
        except (KeyError, ValueError):
            return None

    def uat_sandbox_status(self) -> dict:
        manifest = self.uat_sandbox.current()
        company = self._sandbox_company(manifest)
        entities = dict((manifest or {}).get("entities") or {})
        checks: dict[str, bool] = {}
        if company is not None:
            contact_ids = {row.id for row in self.crm.list_contacts(company.id)}
            opportunity_ids = {row.id for row in self.crm.list_opportunities(company.id)}
            activity_ids = {row.id for row in self.crm.list_activities(company.id)}
            campaign_ids = {row.id for row in self.campaigns.list(company.id)}
            lead_ids = {row.id for row in self.lead_intake.list(company.id)}
            checks = {
                "contact": str(entities.get("contact_id") or "") in contact_ids,
                "matched_lead": str(entities.get("matched_lead_id") or "") in lead_ids,
                "new_lead": str(entities.get("new_lead_id") or "") in lead_ids,
                "opportunity": str(entities.get("opportunity_id") or "") in opportunity_ids,
                "activity": str(entities.get("activity_id") or "") in activity_ids,
                "campaign": str(entities.get("campaign_id") or "") in campaign_ids,
            }
        return {
            "schema": "binario.marketing.uat-sandbox-status.v1",
            "exists": manifest is not None,
            "active": bool(company is not None and company.active),
            "functional_ready": bool(company is not None and company.active and checks and all(checks.values())),
            "generation": (manifest or {}).get("generation"),
            "company": None if company is None else {
                "id": company.id,
                "name": company.name,
                "active": company.active,
            },
            "entities": entities,
            "entity_checks": checks,
            "history_count": len(self.uat_sandbox.history()),
            "contract": {
                "synthetic_data": True,
                "functional_uat_only": True,
                "physical_release_evidence_allowed": False,
                "provider_evidence_seeded": False,
                "results_evidence_seeded": False,
                "automatic_provider_action": False,
                "reset_deactivates_only_recorded_sandbox": True,
                "real_company_mutation_allowed": False,
            },
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "publication_performed": False,
                "paid_activation_performed": False,
                "ai_generation_performed": False,
                "physical_uat_evidence_recorded": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }

    def _create_uat_sandbox_generation(self) -> dict:
        generation = self.uat_sandbox.next_generation()
        company = self.create_company({"name": f"BINARIO UAT Sandbox #{generation:02d}"})
        token = f"g{generation:04d}"
        due_at = (datetime.now(timezone.utc) + timedelta(days=1)).replace(microsecond=0).isoformat()
        try:
            contact = self.create_contact(company["id"], {
                "name": "Cliente UAT Exacto",
                "organization": "Empresa Sintética UAT",
                "email": f"matched.{token}@binario.invalid",
                "phone": f"+570000{generation:06d}",
                "source": "UAT_SANDBOX",
                "tags": ["uat-sandbox", token],
                "notes": "Dato sintético para UAT funcional. No representa un cliente real.",
            })
            matched = self.intake_lead(company["id"], {
                "connector": "MANUAL",
                "source_ref": f"uat-sandbox:{token}:matched",
                "name": "Lead UAT Exacto",
                "email": contact["email"],
                "source": "UAT Sandbox",
                "tags": ["uat-sandbox", "exact-match"],
            })
            new_lead = self.intake_lead(company["id"], {
                "connector": "MANUAL",
                "source_ref": f"uat-sandbox:{token}:new",
                "name": "Lead UAT Nuevo",
                "email": f"new.{token}@binario.invalid",
                "source": "UAT Sandbox",
                "tags": ["uat-sandbox", "new-lead"],
            })
            opportunity = self.create_opportunity(company["id"], {
                "contact_id": contact["id"],
                "title": "Propuesta controlada UAT",
                "stage": "PROPOSAL",
                "value": 1500000,
                "currency": "COP",
                "next_action": "Revisar propuesta UAT y registrar siguiente decisión",
                "next_action_at": due_at,
                "notes": "Oportunidad sintética; nunca sumar con operación real.",
            })
            activity = self.create_activity(company["id"], {
                "contact_id": contact["id"],
                "opportunity_id": opportunity["id"],
                "kind": "TASK",
                "summary": "Seguimiento funcional del sandbox UAT",
                "due_at": due_at,
            })
            campaign = self.create_campaign(company["id"], {
                "name": "Campaña funcional UAT",
                "objective": "LEADS",
                "status": "IN_PROGRESS",
                "channels": ["email", "whatsapp"],
                "audience_contact_ids": [contact["id"]],
                "notes": "Campaña sintética local. Sin publicación, pauta, provider ni resultados sembrados.",
            })
            manifest = self.uat_sandbox.save(
                generation=generation,
                company_id=company["id"],
                company_name=company["name"],
                entities={
                    "contact_id": contact["id"],
                    "matched_lead_id": matched["id"],
                    "new_lead_id": new_lead["id"],
                    "opportunity_id": opportunity["id"],
                    "activity_id": activity["id"],
                    "campaign_id": campaign["id"],
                },
            )
        except Exception:
            self.update_company(company["id"], {"active": False})
            raise
        self.workspace.registries.timeline.append("uat.sandbox.created", {
            "company_id": company["id"],
            "generation": generation,
            "synthetic_data": True,
            "physical_release_evidence_allowed": False,
            "provider_mutation_performed": False,
        })
        if not manifest.get("physical_release_evidence_allowed") is False:
            raise RuntimeError("UAT sandbox release-evidence guard failed")
        return self.uat_sandbox_status()

    def create_uat_sandbox(self, payload: dict) -> dict:
        if payload not in ({}, None):
            if not isinstance(payload, dict):
                raise ValueError("UAT sandbox payload must be an object")
            if payload:
                raise ValueError("UAT sandbox create accepts no fields")
        current = self.uat_sandbox.current()
        company = self._sandbox_company(current)
        if company is not None and company.active:
            return self.uat_sandbox_status()
        return self._create_uat_sandbox_generation()

    def reset_uat_sandbox(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("UAT sandbox reset payload must be an object")
        if set(payload) - {"confirm"}:
            raise ValueError("unsupported UAT sandbox reset fields")
        if payload.get("confirm") is not True:
            raise ValueError("reset requires confirm=true")
        current = self.uat_sandbox.current()
        company = self._sandbox_company(current)
        if company is not None and company.active:
            self.update_company(company.id, {"active": False})
            self.workspace.registries.timeline.append("uat.sandbox.deactivated", {
                "company_id": company.id,
                "generation": (current or {}).get("generation"),
                "real_company_mutation_performed": False,
            })
        return self._create_uat_sandbox_generation()

    def start_physical_uat(self, company_id: str, payload: dict) -> dict:
        if self.uat_sandbox.is_sandbox(company_id):
            raise ValueError(
                "synthetic UAT sandbox is functional-only and cannot record physical release evidence"
            )
        return super().start_physical_uat(company_id, payload)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 75 exposes explicit QA fixture mutations; no provider or release authority is added."""

    def _static(self, path: str) -> None:
        if path == "/interaction-audit.js":
            target = self.server.runtime.repo_root / "web" / "interaction-audit.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave75ControlledUATSandbox(){
  if(document.querySelector('script[data-uat-sandbox-wave75]'))return;
  const sandbox=document.createElement('script');
  sandbox.src='/uat-sandbox.js';
  sandbox.defer=true;
  sandbox.dataset.uatSandboxWave75='1';
  document.head.append(sandbox);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/uat-sandbox.js":
            self._static(path)
            return
        if path == "/api/uat-sandbox":
            try:
                self._json(self.server.runtime.uat_sandbox_status())
            except Exception as exc:
                self._wave67_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/uat-sandbox":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_uat_sandbox(self._body()), HTTPStatus.CREATED)
                return
            if path == "/api/uat-sandbox/reset":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.reset_uat_sandbox(self._body()), HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave67_error(exc)
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
