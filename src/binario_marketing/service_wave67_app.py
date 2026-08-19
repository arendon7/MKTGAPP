from __future__ import annotations

import json
import os
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_wave66_app as base
from .physical_uat_store import PhysicalUATStore
from .version import RELEASE_READY, RELEASE_TAG, __version__


class AppRuntime(base.AppRuntime):
    """Wave 67 records explicit local evidence for physical UAT without opening release gates."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.physical_uat = PhysicalUATStore(runtime.data_root / "physical_uat")
        return runtime

    def _build_provenance(self) -> dict:
        candidates = [
            self.repo_root / "BUILD_PROVENANCE.json",
            self.repo_root.parent / "BUILD_PROVENANCE.json",
        ]
        for path in candidates:
            if not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                continue
            if isinstance(payload, dict):
                return {
                    "source": "BUILD_PROVENANCE.json",
                    "git_sha": payload.get("git_sha"),
                    "architecture": payload.get("architecture"),
                    "product_version": payload.get("product_version") or payload.get("version") or __version__,
                    "release_channel": payload.get("release_channel") or "development",
                    "signing_mode": payload.get("signing_mode") or payload.get("signing") or "ad_hoc",
                    "notarized": bool(payload.get("notarized")),
                }
        return {
            "source": "SOURCE_CHECKOUT",
            "git_sha": os.environ.get("GITHUB_SHA"),
            "architecture": None,
            "product_version": __version__,
            "release_channel": "development",
            "signing_mode": "ad_hoc",
            "notarized": False,
        }

    def physical_uat_overview(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        sessions = self.physical_uat.list(company.id, limit=20)
        readiness = self.product_uat_readiness(company.id)
        active = next((row for row in sessions if row.get("status") == "IN_PROGRESS"), None)
        complete = next((row for row in sessions if row.get("physical_uat_complete")), None)
        return {
            "schema": "binario.marketing.physical-uat-overview.v1",
            "company": {"id": company.id, "name": company.name},
            "readiness": readiness,
            "active_session": active,
            "latest_session": sessions[0] if sessions else None,
            "sessions": [{
                "id": row.get("id"),
                "status": row.get("status"),
                "created_at": row.get("created_at"),
                "finished_at": row.get("finished_at"),
                "operator": row.get("operator"),
                "machine": row.get("machine"),
                "evidence_sha256": row.get("evidence_sha256"),
                "physical_uat_complete": bool(row.get("physical_uat_complete")),
            } for row in sessions],
            "physical_uat_recorded": bool(sessions),
            "physical_uat_complete": complete is not None,
            "release_boundary": {
                "version": __version__,
                "release_ready": RELEASE_READY,
                "release_tag": RELEASE_TAG,
                "distribution_signing_certified": False,
                "notarization_certified": False,
                "production_ready": False,
            },
            "safety": {
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "marketing_mutation_performed": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }

    def start_physical_uat(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("physical UAT payload must be an object")
        unknown = set(payload) - {"operator", "notes"}
        if unknown:
            raise ValueError(f"unsupported physical UAT fields: {', '.join(sorted(unknown))}")
        company = self.companies.get(company_id)
        readiness = self.product_uat_readiness(company.id)
        row = self.physical_uat.create(
            company.id,
            scenarios=list(readiness.get("manual_scenarios") or []),
            build=self._build_provenance(),
            operator=payload.get("operator"),
            notes=payload.get("notes"),
        )
        self.workspace.registries.timeline.append("uat.physical.started", {
            "company_id": company.id,
            "session_id": row["id"],
            "physical_gate_eligible": bool((row.get("machine") or {}).get("physical_gate_eligible")),
            "explicit_user_action": True,
            "marketing_mutation_performed": False,
            "provider_mutation_performed": False,
        })
        return row

    def update_physical_uat_scenario(
        self,
        company_id: str,
        session_id: str,
        scenario_id: str,
        payload: dict,
    ) -> dict:
        company = self.companies.get(company_id)
        row = self.physical_uat.update_scenario(company.id, session_id, scenario_id, payload)
        scenario = next(item for item in row.get("scenarios") or [] if item.get("id") == scenario_id)
        self.workspace.registries.timeline.append("uat.physical.scenario_recorded", {
            "company_id": company.id,
            "session_id": row["id"],
            "scenario_id": scenario_id,
            "status": scenario.get("status"),
            "explicit_user_action": True,
            "marketing_mutation_performed": False,
            "provider_mutation_performed": False,
        })
        return row

    def finish_physical_uat(self, company_id: str, session_id: str) -> dict:
        company = self.companies.get(company_id)
        readiness = self.product_uat_readiness(company.id)
        row = self.physical_uat.finish(company.id, session_id, readiness=readiness)
        self.workspace.registries.timeline.append("uat.physical.finished", {
            "company_id": company.id,
            "session_id": row["id"],
            "status": row.get("status"),
            "physical_gate_eligible": bool((row.get("machine") or {}).get("physical_gate_eligible")),
            "physical_uat_complete": bool(row.get("physical_uat_complete")),
            "evidence_sha256": row.get("evidence_sha256"),
            "release_ready_changed": False,
            "explicit_user_action": True,
        })
        return row

    def physical_uat_report(self, company_id: str, session_id: str) -> dict:
        company = self.companies.get(company_id)
        report = self.physical_uat.report(company.id, session_id)
        report["company"] = {"id": company.id, "name": company.name}
        report["release_boundary"] = {
            "version": __version__,
            "release_ready": RELEASE_READY,
            "release_tag": RELEASE_TAG,
            "distribution_signing_certified": False,
            "notarization_certified": False,
            "production_ready": False,
        }
        return report


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 67 exposes only explicit local QA mutations; no marketing/provider authority is added."""

    def _wave67_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def _static(self, path: str) -> None:
        if path == "/uat-readiness.js":
            target = self.server.runtime.repo_root / "web" / "uat-readiness.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave67PhysicalUAT(){
  if(document.querySelector('script[data-physical-uat-wave67]'))return;
  const physical=document.createElement('script');
  physical.src='/physical-uat.js';
  physical.defer=true;
  physical.dataset.physicalUatWave67='1';
  document.head.append(physical);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/physical-uat.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "physical-uat":
                self._json(self.server.runtime.physical_uat_overview(parts[2]))
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "physical-uat"
                and parts[5] == "report"
            ):
                self._json(self.server.runtime.physical_uat_report(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave67_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "physical-uat":
                with self.server.mutation_lock:
                    result = self.server.runtime.start_physical_uat(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if (
                len(parts) == 6
                and parts[:2] == ["api", "companies"]
                and parts[3] == "physical-uat"
                and parts[5] == "finish"
            ):
                with self.server.mutation_lock:
                    result = self.server.runtime.finish_physical_uat(parts[2], parts[4])
                self._json(result)
                return
        except Exception as exc:
            self._wave67_error(exc)
            return
        super().do_POST()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if (
                len(parts) == 7
                and parts[:2] == ["api", "companies"]
                and parts[3] == "physical-uat"
                and parts[5] == "scenarios"
            ):
                with self.server.mutation_lock:
                    result = self.server.runtime.update_physical_uat_scenario(
                        parts[2], parts[4], parts[6], self._body()
                    )
                self._json(result)
                return
        except Exception as exc:
            self._wave67_error(exc)
            return
        super().do_PATCH()


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
