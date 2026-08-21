from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_wave70_app as base


def _stable_digest(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class AppRuntime(base.AppRuntime):
    """Wave 71 consolidates physical-UAT and release evidence into one read-only candidate dossier."""

    def candidate_certification_dossier(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        readiness = self.product_uat_readiness(company.id)
        preflight = self.physical_uat_preflight(company.id)
        evidence = self.release_evidence(company.id)
        sessions = self.physical_uat.list(company.id, limit=20)
        latest = sessions[0] if sessions else None

        preflight_ready = bool(preflight.get("ready_to_begin_physical_uat"))
        uat_accepted = bool(evidence.get("physical_uat", {}).get("accepted_for_current_build"))
        release_readiness = evidence.get("release_readiness") or {}
        blockers = list(release_readiness.get("blocker_codes") or [])
        active_session = next((row for row in sessions if row.get("status") == "IN_PROGRESS"), None)

        if uat_accepted:
            stage = "PHYSICAL_UAT_PASSED_FOR_BUILD"
            next_action = "Resolve remaining independent release blockers"
        elif active_session is not None:
            stage = "PHYSICAL_UAT_IN_PROGRESS"
            next_action = "Complete every required UAT scenario explicitly"
        elif preflight_ready:
            stage = "READY_FOR_PHYSICAL_UAT"
            next_action = "Start guided physical UAT on this exact Mac build"
        else:
            stage = "BLOCKED_PREFLIGHT"
            next_action = "Resolve physical UAT preflight blockers before starting evidence"

        scenario_rows = []
        for row in readiness.get("manual_scenarios") or []:
            scenario_rows.append({
                "id": row.get("id"),
                "title": row.get("title"),
                "required": bool(row.get("required")),
                "view": row.get("view"),
                "precondition": row.get("precondition"),
                "expected": row.get("expected"),
            })

        session_summary = None
        if latest is not None:
            scenarios = list(latest.get("scenarios") or [])
            session_summary = {
                "id": latest.get("id"),
                "status": latest.get("status"),
                "operator": latest.get("operator"),
                "started_at": latest.get("started_at"),
                "finished_at": latest.get("finished_at"),
                "physical_uat_complete": bool(latest.get("physical_uat_complete")),
                "evidence_sha256": latest.get("evidence_sha256"),
                "required_pass": sum(1 for row in scenarios if row.get("required") and row.get("status") == "PASS"),
                "required_total": sum(1 for row in scenarios if row.get("required")),
                "failed": sum(1 for row in scenarios if row.get("status") == "FAIL"),
                "blocked": sum(1 for row in scenarios if row.get("status") == "BLOCKED"),
            }

        canonical = {
            "company": {"id": company.id, "name": company.name},
            "candidate": evidence.get("current_build") or {},
            "stage": stage,
            "preflight": {
                "ready": preflight_ready,
                "checks": preflight.get("checks") or [],
                "blockers": preflight.get("blockers") or [],
            },
            "uat": {
                "accepted_for_current_build": uat_accepted,
                "latest_session": session_summary,
                "required_scenarios": scenario_rows,
            },
            "release": {
                "stage": release_readiness.get("stage"),
                "production_ready": bool(release_readiness.get("production_ready")),
                "blocker_codes": blockers,
            },
        }
        dossier_sha256 = _stable_digest(canonical)
        return {
            "schema": "binario.marketing.candidate-certification-dossier.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **canonical,
            "next_action": next_action,
            "dossier_sha256": dossier_sha256,
            "governance": {
                "dossier_is_release_authority": False,
                "physical_uat_evidence_authority": "W67",
                "release_readiness_authority": "W46 evaluator via W70",
                "candidate_identity_requires_exact_build": True,
                "export_is_snapshot_only": True,
            },
            "safety": {
                "read_only": True,
                "release_state_mutation_performed": False,
                "physical_uat_mutation_performed": False,
                "marketing_mutation_performed": False,
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 71 adds one GET-only certification dossier and browser export surface."""

    def _static(self, path: str) -> None:
        if path == "/release-evidence.js":
            target = self.server.runtime.repo_root / "web" / "release-evidence.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave71CandidateDossier(){
  if(document.querySelector('script[data-candidate-dossier-wave71]'))return;
  const dossier=document.createElement('script');
  dossier.src='/candidate-certification-dossier.js';
  dossier.defer=true;
  dossier.dataset.candidateDossierWave71='1';
  document.head.append(dossier);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/candidate-certification-dossier.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "certification-dossier":
                self._json(self.server.runtime.candidate_certification_dossier(parts[2]))
                return
        except Exception as exc:
            self._wave67_error(exc)
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
