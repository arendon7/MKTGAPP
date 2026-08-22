#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE_A_SCHEMA = "binario.marketing.physical-uat-evidence.v1"
PHASE_B_SCHEMA = "binario.marketing.release-uat-evidence.v1"
CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
ATTESTATION_SCHEMA = "binario.marketing.combined-physical-uat-attestation.v1"
EXPECTED_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 84
REQUIRED_PHASE_B_IDS = {
    "launcher_relaunch",
    "persistence",
    "company_crm",
    "today_complete",
    "today_reschedule",
    "content_library",
    "social_readonly",
    "manual_reply",
    "editorial_management",
    "video_import_render",
    "transcription",
    "credentials",
}


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _candidate(app: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    resources = app / "Contents" / "Resources"
    candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    provenance_path = resources / "BUILD_PROVENANCE.json"
    _require(candidate_path.is_file(), "candidate manifest missing")
    _require(provenance_path.is_file(), "build provenance missing")
    candidate = _load(candidate_path)
    provenance = _load(provenance_path)
    _require(candidate.get("schema") == CANDIDATE_SCHEMA, "unexpected candidate schema")
    _require(candidate.get("role") == EXPECTED_ROLE, "candidate is not physical-UAT eligible")
    _require(candidate.get("trusted_for_physical_uat") is True, "candidate origin is not trusted for physical UAT")
    origin = candidate.get("build_origin") or {}
    _require(origin.get("trusted_for_physical_uat") is True, "candidate build origin is not trusted")
    _require(origin.get("event_name") == "push", "physical candidate must originate from a push")
    ref = str(origin.get("ref") or "")
    _require(ref == "refs/heads/main" or ref.startswith("refs/tags/v"), "physical candidate must originate from main or a version tag")
    _require(candidate.get("architecture") == "arm64", "physical candidate must be arm64")
    _require(candidate.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "candidate runtime wave drift")
    _require(candidate.get("certification_guard_wave") == EXPECTED_GUARD_WAVE, "candidate guard wave drift")
    _require(candidate.get("git_sha") == provenance.get("git_sha"), "candidate/provenance git SHA mismatch")
    _require(candidate.get("product_version") == provenance.get("product_version"), "candidate/provenance version mismatch")
    boundary = candidate.get("release_boundary") or {}
    _require(boundary.get("release_ready") is False, "candidate unexpectedly carries release-ready authority")
    _require(boundary.get("release_tag") is None, "candidate unexpectedly carries a release tag")
    _require(boundary.get("production_ready") is False, "candidate unexpectedly reports production-ready")
    return candidate, candidate_path, provenance


def _validate_phase_a(report: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    _require(report.get("schema") == PHASE_A_SCHEMA, "invalid Phase A evidence schema")
    _require(report.get("release_authority") is False, "Phase A evidence unexpectedly has release authority")
    session = report.get("session") or {}
    _require(isinstance(session, dict), "Phase A session missing")
    _require(session.get("status") == "PASSED", "Phase A session is not PASSED")
    _require(session.get("physical_uat_complete") is True, "Phase A physical_uat_complete is not true")
    machine = session.get("machine") or {}
    _require(machine.get("system") == "Darwin", "Phase A was not recorded on Darwin")
    _require(str(machine.get("machine") or "").lower() == "arm64", "Phase A was not recorded on arm64")
    _require(machine.get("is_ci") is False, "Phase A cannot come from CI")
    _require(machine.get("physical_gate_eligible") is True, "Phase A machine is not physical-gate eligible")

    scenarios = session.get("scenarios") or []
    _require(isinstance(scenarios, list) and scenarios, "Phase A scenarios missing")
    required = [row for row in scenarios if isinstance(row, dict) and row.get("required")]
    _require(bool(required), "Phase A required scenarios missing")
    _require(all(row.get("status") == "PASS" for row in required), "Phase A required scenarios are not all PASS")

    expected_evidence_sha = str(session.get("evidence_sha256") or "")
    evidence = dict(session)
    evidence["evidence_sha256"] = None
    actual_evidence_sha = _digest(evidence)
    _require(expected_evidence_sha == actual_evidence_sha, "Phase A session evidence digest mismatch")

    build = session.get("build") or {}
    _require(build.get("git_sha") == candidate.get("git_sha"), "Phase A git SHA mismatch")
    _require(str(build.get("architecture") or "").lower() == "arm64", "Phase A architecture mismatch")
    _require(build.get("product_version") == candidate.get("product_version"), "Phase A product version mismatch")
    _require(build.get("source") == "BUILD_PROVENANCE.json", "Phase A did not use bundled build provenance")

    summary = report.get("summary") or {}
    _require(summary.get("physical_uat_complete") is True, "Phase A summary is not complete")
    _require(int(summary.get("failed") or 0) == 0, "Phase A summary contains failures")
    _require(int(summary.get("blocked") or 0) == 0, "Phase A summary contains blockers")
    _require(int(summary.get("pending") or 0) == 0, "Phase A summary contains pending required scenarios")
    _require(int(summary.get("passed") or 0) == len(required), "Phase A summary/pass count mismatch")

    return {
        "session_id": session.get("id"),
        "evidence_sha256": expected_evidence_sha,
        "required_scenarios": len(required),
        "passed_scenarios": len(required),
        "finished_at": session.get("finished_at"),
    }


def _validate_phase_b(report: dict[str, Any], candidate: dict[str, Any], candidate_manifest_sha: str) -> dict[str, Any]:
    _require(report.get("schema") == PHASE_B_SCHEMA, "invalid Phase B evidence schema")
    _require(report.get("git_sha") == candidate.get("git_sha"), "Phase B git SHA mismatch")
    _require(report.get("architecture") == "arm64", "Phase B architecture mismatch")
    _require(report.get("version") == candidate.get("product_version"), "Phase B product version mismatch")
    _require(report.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "Phase B runtime wave mismatch")
    _require(report.get("candidate_source_sha256") == candidate.get("candidate_source_sha256"), "Phase B candidate source digest mismatch")
    _require(report.get("candidate_manifest_sha256") == candidate_manifest_sha, "Phase B candidate manifest digest mismatch")
    _require(report.get("automatic_passed") is True, "Phase B automatic checks did not pass")
    _require(report.get("uat_passed") is True, "Phase B uat_passed is not true")
    _require(report.get("overall") == "UAT_PASS", "Phase B overall result is not UAT_PASS")

    manual = report.get("manual_steps") or []
    _require(isinstance(manual, list), "Phase B manual steps missing")
    ids = {str(row.get("id")) for row in manual if isinstance(row, dict)}
    _require(ids == REQUIRED_PHASE_B_IDS, "Phase B manual gate set drift")
    _require(len(manual) == len(REQUIRED_PHASE_B_IDS), "Phase B manual gate count drift")
    for row in manual:
        _require(isinstance(row, dict), "invalid Phase B manual gate")
        _require(row.get("status") == "PASS", f"Phase B gate is not PASS: {row.get('id')}")
        _require(bool(str(row.get("note") or "").strip()), f"Phase B gate lacks concrete note: {row.get('id')}")
        _require(bool(str(row.get("recorded_at") or "").strip()), f"Phase B gate lacks recorded_at: {row.get('id')}")

    return {
        "required_gates": len(REQUIRED_PHASE_B_IDS),
        "passed_gates": len(REQUIRED_PHASE_B_IDS),
        "overall": "UAT_PASS",
        "updated_at": report.get("updated_at"),
    }


def finalize(app: Path, phase_a_path: Path, phase_b_path: Path) -> dict[str, Any]:
    app = app.expanduser().resolve()
    phase_a_path = phase_a_path.expanduser().resolve()
    phase_b_path = phase_b_path.expanduser().resolve()
    _require(app.is_dir(), f"app bundle missing: {app}")
    _require(phase_a_path.is_file(), f"Phase A evidence missing: {phase_a_path}")
    _require(phase_b_path.is_file(), f"Phase B evidence missing: {phase_b_path}")

    candidate, candidate_path, provenance = _candidate(app)
    candidate_manifest_sha = _sha256_file(candidate_path)
    phase_a = _load(phase_a_path)
    phase_b = _load(phase_b_path)
    phase_a_summary = _validate_phase_a(phase_a, candidate)
    phase_b_summary = _validate_phase_b(phase_b, candidate, candidate_manifest_sha)

    binding = {
        "git_sha": candidate.get("git_sha"),
        "product_version": candidate.get("product_version"),
        "architecture": "arm64",
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "candidate_source_sha256": candidate.get("candidate_source_sha256"),
        "candidate_manifest_sha256": candidate_manifest_sha,
        "build_origin": candidate.get("build_origin"),
        "provenance_schema": provenance.get("schema"),
    }
    core = {
        "schema": ATTESTATION_SCHEMA,
        "binding": binding,
        "phase_a": {
            **phase_a_summary,
            "report_sha256": _sha256_file(phase_a_path),
        },
        "phase_b": {
            **phase_b_summary,
            "report_sha256": _sha256_file(phase_b_path),
        },
        "both_phases_passed": True,
        "release_authority": False,
        "production_ready": False,
    }
    attestation_sha = _digest(core)
    return {
        **core,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "attestation_sha256": attestation_sha,
    }


def render_markdown(report: dict[str, Any]) -> str:
    b = report["binding"]
    a = report["phase_a"]
    p = report["phase_b"]
    return "\n".join([
        "# BINARIO Marketing IA · Combined Physical UAT Attestation",
        "",
        f"- Git SHA: `{b['git_sha']}`",
        f"- Version: `{b['product_version']}`",
        f"- Architecture: `{b['architecture']}`",
        f"- Runtime: `Wave {b['runtime_wave']}`",
        f"- Candidate source SHA-256: `{b['candidate_source_sha256']}`",
        f"- Candidate manifest SHA-256: `{b['candidate_manifest_sha256']}`",
        f"- Phase A: **PASS** · {a['passed_scenarios']}/{a['required_scenarios']} required scenarios",
        f"- Phase B: **PASS** · {p['passed_gates']}/{p['required_gates']} release gates",
        f"- Combined attestation SHA-256: `{report['attestation_sha256']}`",
        "- Release authority: **NO**",
        "- Production ready: **NO**",
        "",
        "This attestation proves only that both physical UAT evidence layers passed on the same trusted exact candidate. It does not enable release flags, signing, notarization or publication.",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize Phase A + Phase B physical UAT for one exact trusted BINARIO arm64 candidate.")
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--phase-a", type=Path, required=True)
    parser.add_argument("--phase-b", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = finalize(args.app, args.phase_a, args.phase_b)
    except ValueError as exc:
        raise SystemExit(f"COMBINED PHYSICAL UAT BLOCKED: {exc}") from exc
    out = args.output.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "combined-physical-uat-attestation.json"
    md_path = out / "combined-physical-uat-attestation.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({
        "both_phases_passed": report["both_phases_passed"],
        "git_sha": report["binding"]["git_sha"],
        "attestation_sha256": report["attestation_sha256"],
        "output": str(json_path),
        "release_authority": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
