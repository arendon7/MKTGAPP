from __future__ import annotations

import hashlib
import json
from http import HTTPStatus
from urllib.parse import urlparse

from . import service_wave69_app as base
from .release_readiness import evaluate_release_readiness
from .version import RELEASE_READY, RELEASE_TAG, __version__


def _evidence_digest(row: dict) -> str:
    evidence = dict(row)
    evidence["evidence_sha256"] = None
    encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _normalized_build(build: dict | None) -> dict:
    source = dict(build or {})
    return {
        "source": str(source.get("source") or ""),
        "git_sha": str(source.get("git_sha") or "").strip().lower() or None,
        "architecture": str(source.get("architecture") or "").strip().lower() or None,
        "product_version": str(source.get("product_version") or source.get("version") or "").strip() or None,
        "release_channel": str(source.get("release_channel") or "").strip().lower() or None,
        "signing_mode": str(source.get("signing_mode") or source.get("signing") or "").strip().lower() or None,
        "notarized": bool(source.get("notarized")),
    }


def _session_validation(session: dict, current_build: dict) -> dict:
    build = _normalized_build(session.get("build"))
    current = _normalized_build(current_build)
    scenarios = list(session.get("scenarios") or [])
    required = [row for row in scenarios if row.get("required")]
    expected_digest = str(session.get("evidence_sha256") or "").strip().lower()
    actual_digest = _evidence_digest(session)
    digest_valid = bool(expected_digest) and expected_digest == actual_digest
    machine = session.get("machine") or {}
    machine_eligible = bool(machine.get("physical_gate_eligible")) and not bool(machine.get("is_ci"))
    all_required_pass = bool(required) and all(row.get("status") == "PASS" for row in required)
    build_match = {
        "git_sha": bool(current.get("git_sha")) and build.get("git_sha") == current.get("git_sha"),
        "architecture": current.get("architecture") == "arm64" and build.get("architecture") == current.get("architecture"),
        "product_version": current.get("product_version") == __version__ and build.get("product_version") == current.get("product_version"),
    }
    build_exact = all(build_match.values())
    valid = bool(
        session.get("status") == "PASSED"
        and session.get("physical_uat_complete") is True
        and machine_eligible
        and all_required_pass
        and digest_valid
        and build_exact
    )
    reasons: list[str] = []
    if session.get("status") != "PASSED":
        reasons.append("session_not_passed")
    if session.get("physical_uat_complete") is not True:
        reasons.append("physical_uat_not_complete")
    if not machine_eligible:
        reasons.append("machine_ineligible")
    if not all_required_pass:
        reasons.append("required_scenarios_not_all_pass")
    if not digest_valid:
        reasons.append("evidence_digest_mismatch")
    if not build_match["git_sha"]:
        reasons.append("git_sha_mismatch")
    if not build_match["architecture"]:
        reasons.append("architecture_mismatch")
    if not build_match["product_version"]:
        reasons.append("version_mismatch")
    return {
        "session_id": session.get("id"),
        "status": session.get("status"),
        "finished_at": session.get("finished_at"),
        "evidence_sha256": expected_digest or None,
        "digest_valid": digest_valid,
        "machine_eligible": machine_eligible,
        "all_required_pass": all_required_pass,
        "build": build,
        "build_match": build_match,
        "build_exact_match": build_exact,
        "accepted_for_current_build": valid,
        "rejection_reasons": reasons,
    }


class AppRuntime(base.AppRuntime):
    """Wave 70 bridges physical-UAT evidence into release readiness without granting release authority."""

    def release_evidence(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        current_build = self._build_provenance()
        sessions = self.physical_uat.list(company.id, limit=100)
        validations = [_session_validation(row, current_build) for row in sessions]
        accepted = next((row for row in validations if row["accepted_for_current_build"]), None)
        current = _normalized_build(current_build)
        readiness = evaluate_release_readiness(
            version=__version__,
            release_ready=RELEASE_READY,
            release_tag=RELEASE_TAG,
            signing_mode=current.get("signing_mode") or "ad_hoc",
            notarized=current.get("notarized"),
            uat_passed=accepted is not None,
            git_sha=current.get("git_sha"),
            architecture=current.get("architecture"),
        )
        return {
            "schema": "binario.marketing.release-evidence.v1",
            "company": {"id": company.id, "name": company.name},
            "current_build": current,
            "physical_uat": {
                "accepted": accepted,
                "accepted_for_current_build": accepted is not None,
                "sessions_checked": len(validations),
                "latest_validation": validations[0] if validations else None,
                "validations": validations[:20],
                "acceptance_contract": {
                    "session_status": "PASSED",
                    "physical_uat_complete": True,
                    "machine": "Darwin arm64 non-CI",
                    "all_required_scenarios": "PASS",
                    "evidence_digest": "MATCH",
                    "git_sha": "EXACT_MATCH",
                    "architecture": "arm64 EXACT_MATCH",
                    "product_version": __version__,
                },
            },
            "release_readiness": readiness,
            "release_boundary": {
                "release_ready": RELEASE_READY,
                "release_tag": RELEASE_TAG,
                "physical_uat_can_remove_only_uat_blocker": True,
                "physical_uat_can_change_source_release_contract": False,
                "physical_uat_can_change_signing_or_notarization": False,
                "production_ready": bool(readiness.get("production_ready")),
            },
            "safety": {
                "read_only": True,
                "release_state_mutation_performed": False,
                "provider_read_performed": False,
                "provider_mutation_performed": False,
                "marketing_mutation_performed": False,
                "background_polling": False,
                "cloud_required": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Wave 70 exposes a GET-only evidence/readiness projection and browser status panel."""

    def _static(self, path: str) -> None:
        if path == "/physical-uat-preflight.js":
            target = self.server.runtime.repo_root / "web" / "physical-uat-preflight.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadWave70ReleaseEvidence(){
  if(document.querySelector('script[data-release-evidence-wave70]'))return;
  const evidence=document.createElement('script');
  evidence.src='/release-evidence.js';
  evidence.defer=true;
  evidence.dataset.releaseEvidenceWave70='1';
  document.head.append(evidence);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/release-evidence.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if (
                len(parts) == 4
                and parts[:2] == ["api", "companies"]
                and parts[3] == "release-evidence"
            ):
                self._json(self.server.runtime.release_evidence(parts[2]))
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
