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
EXPECTED_CANDIDATE_GUARD_WAVE = 84
ATTESTATION_WAVE = 85
SOURCE_CONTRACT_WAVE = 95
LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"
REQUIRED_PHASE_A_IDS = {
    "company-switch", "inbox-to-crm", "pipeline-followup",
    "campaign-execution", "results-decision",
}
OPTIONAL_PHASE_A_IDS = {"optional-ai"}
CANONICAL_PHASE_A_IDS = REQUIRED_PHASE_A_IDS | OPTIONAL_PHASE_A_IDS
REQUIRED_PHASE_B_IDS = {
    "launcher_relaunch", "persistence", "company_crm", "today_complete",
    "today_reschedule", "content_library", "social_readonly", "manual_reply",
    "editorial_management", "video_import_render", "transcription", "credentials",
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


def _source_digest(source: Path) -> str:
    """Recompute the exact W81/W95 source identity from the extracted app."""
    digest = hashlib.sha256()
    files: list[Path] = []
    for root in (source / "src", source / "web", source / "apps"):
        if not root.is_dir():
            raise ValueError(f"candidate source root missing: {root}")
        files.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(source).as_posix()):
        relative = path.relative_to(source).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
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


def _candidate_source_contract(candidate: dict[str, Any]) -> tuple[str, str | None]:
    boundary = candidate.get("release_boundary") or {}
    _require(isinstance(boundary, dict), "candidate release boundary missing")
    version = str(candidate.get("product_version") or "")
    state = candidate.get("source_release_state") or boundary.get("source_release_state")
    ready = boundary.get("release_ready")
    tag = boundary.get("release_tag")
    if state is None and ready is False and tag is None:
        state = LOCKED_SOURCE
    _require(boundary.get("operational_authorization") in {None, False}, "candidate unexpectedly carries operational authority")
    _require(boundary.get("release_authority") in {None, False}, "candidate unexpectedly carries release authority")
    _require(boundary.get("publication_authority") in {None, False}, "candidate unexpectedly carries publication authority")
    _require(boundary.get("production_ready") is False, "candidate unexpectedly reports production-ready")
    if state == LOCKED_SOURCE:
        _require(ready is False and tag is None, "LOCKED_SOURCE candidate release boundary drift")
    elif state == PREPARED_RELEASE:
        _require(ready is True, "PREPARED_RELEASE candidate must have RELEASE_READY=True in source")
        _require(tag == f"v{version}", "PREPARED_RELEASE candidate tag/version mismatch")
        _require(".dev" not in version.lower() and "rc" not in version.lower(), "PREPARED_RELEASE candidate version is not stable")
    else:
        raise ValueError("candidate source release state is missing or invalid")
    return str(state), str(tag) if tag is not None else None


def _load_candidate(app: Path) -> tuple[dict[str, Any], Path, dict[str, Any], str, str | None]:
    resources = app / "Contents" / "Resources"
    source = resources / "source"
    candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    provenance_path = resources / "BUILD_PROVENANCE.json"
    _require(candidate_path.is_file(), "candidate manifest missing")
    _require(provenance_path.is_file(), "build provenance missing")
    candidate = _load(candidate_path)
    provenance = _load(provenance_path)
    origin = candidate.get("build_origin") or {}
    ref = str(origin.get("ref") or "")
    _require(candidate.get("schema") == CANDIDATE_SCHEMA, "unexpected candidate schema")
    _require(candidate.get("role") == EXPECTED_ROLE, "candidate is not physical-UAT eligible")
    _require(origin.get("event") == "push", "physical candidate must originate from a push")
    _require(origin.get("trusted_for_physical_uat") is True, "candidate build origin is not trusted")
    _require(ref == "refs/heads/main", "physical candidate must originate from canonical main")
    _require(candidate.get("architecture") == "arm64", "physical candidate must be arm64")
    _require(candidate.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "candidate runtime wave drift")
    _require(candidate.get("certification_guard_wave") == EXPECTED_CANDIDATE_GUARD_WAVE, "candidate guard wave drift")
    _require(candidate.get("source_contract_wave") in {None, SOURCE_CONTRACT_WAVE}, "candidate source contract wave drift")
    _require(candidate.get("git_sha") == provenance.get("git_sha"), "candidate/provenance git SHA mismatch")
    _require(candidate.get("product_version") == provenance.get("product_version"), "candidate/provenance version mismatch")
    physical = candidate.get("physical_uat") or {}
    _require(physical.get("eligible_build_origin") is True, "candidate is not physical-UAT origin eligible")
    _require(physical.get("automatic_pass") is False, "candidate cannot carry automatic physical UAT PASS")
    source_state, source_tag = _candidate_source_contract(candidate)
    expected_source_sha = str(candidate.get("candidate_source_sha256") or "")
    _require(len(expected_source_sha) == 64, "candidate source digest missing or malformed")
    _require(_source_digest(source) == expected_source_sha, "candidate source digest does not match extracted app")
    return candidate, candidate_path, provenance, source_state, source_tag


def _phase_a(report: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    _require(report.get("schema") == PHASE_A_SCHEMA, "invalid Phase A evidence schema")
    _require(report.get("release_authority") is False, "Phase A unexpectedly has release authority")
    session = report.get("session") or {}
    machine = session.get("machine") or {}
    _require(session.get("status") == "PASSED", "Phase A session is not PASSED")
    _require(session.get("physical_uat_complete") is True, "Phase A physical_uat_complete is not true")
    _require(machine.get("system") == "Darwin", "Phase A was not recorded on Darwin")
    _require(str(machine.get("machine") or "").lower() == "arm64", "Phase A was not recorded on arm64")
    _require(machine.get("is_ci") is False, "Phase A cannot come from CI")
    _require(machine.get("physical_gate_eligible") is True, "Phase A machine is not physical-gate eligible")

    scenarios = session.get("scenarios")
    _require(isinstance(scenarios, list), "Phase A scenario contract missing")
    _require(all(isinstance(row, dict) for row in scenarios), "Phase A scenario rows must be objects")
    scenario_ids = [str(row.get("id") or "") for row in scenarios]
    _require(len(scenario_ids) == len(CANONICAL_PHASE_A_IDS), "Phase A scenario count drift")
    _require(len(set(scenario_ids)) == len(scenario_ids), "Phase A scenario ids contain duplicates")
    _require(set(scenario_ids) == CANONICAL_PHASE_A_IDS, "Phase A scenario contract drift")
    for row in scenarios:
        scenario_id = str(row.get("id") or "")
        expected_required = scenario_id in REQUIRED_PHASE_A_IDS
        _require(row.get("required") is expected_required, f"Phase A required flag drift: {scenario_id}")

    required = [row for row in scenarios if row.get("required")]
    required_ids = {str(row.get("id") or "") for row in required}
    _require(
        required_ids == REQUIRED_PHASE_A_IDS and len(required) == len(REQUIRED_PHASE_A_IDS),
        "Phase A required scenario set drift",
    )
    _require(all(row.get("status") == "PASS" for row in required), "Phase A required scenarios are not all PASS")

    expected_digest = str(session.get("evidence_sha256") or "")
    digest_payload = dict(session)
    digest_payload["evidence_sha256"] = None
    _require(expected_digest == _digest(digest_payload), "Phase A session evidence digest mismatch")

    build = session.get("build") or {}
    _require(build.get("source") == "BUILD_PROVENANCE.json", "Phase A did not use bundled build provenance")
    _require(build.get("git_sha") == candidate.get("git_sha"), "Phase A git SHA mismatch")
    _require(str(build.get("architecture") or "").lower() == "arm64", "Phase A architecture mismatch")
    _require(build.get("product_version") == candidate.get("product_version"), "Phase A product version mismatch")

    summary = report.get("summary") or {}
    _require(summary.get("physical_uat_complete") is True, "Phase A summary is not complete")
    _require(int(summary.get("required") or 0) == len(REQUIRED_PHASE_A_IDS), "Phase A summary/required count mismatch")
    summary_required_ids = summary.get("required_scenario_ids")
    if summary_required_ids is not None:
        _require(
            isinstance(summary_required_ids, list) and set(map(str, summary_required_ids)) == REQUIRED_PHASE_A_IDS and len(summary_required_ids) == len(REQUIRED_PHASE_A_IDS),
            "Phase A summary required scenario ids drift",
        )
    summary_optional_ids = summary.get("optional_scenario_ids")
    if summary_optional_ids is not None:
        _require(
            isinstance(summary_optional_ids, list) and set(map(str, summary_optional_ids)) == OPTIONAL_PHASE_A_IDS and len(summary_optional_ids) == len(OPTIONAL_PHASE_A_IDS),
            "Phase A summary optional scenario ids drift",
        )
    _require(int(summary.get("failed") or 0) == 0, "Phase A summary contains failures")
    _require(int(summary.get("blocked") or 0) == 0, "Phase A summary contains blockers")
    _require(int(summary.get("pending") or 0) == 0, "Phase A summary contains pending required scenarios")
    _require(int(summary.get("passed") or 0) == len(required), "Phase A summary/pass count mismatch")
    return {
        "session_id": session.get("id"),
        "evidence_sha256": expected_digest,
        "required_scenarios": len(required),
        "passed_scenarios": len(required),
        "required_scenario_ids": sorted(REQUIRED_PHASE_A_IDS),
        "optional_scenario_ids": sorted(OPTIONAL_PHASE_A_IDS),
        "finished_at": session.get("finished_at"),
    }


def _phase_b(report: dict[str, Any], candidate: dict[str, Any], manifest_sha: str, source_state: str, source_tag: str | None) -> dict[str, Any]:
    _require(report.get("schema") == PHASE_B_SCHEMA, "invalid Phase B evidence schema")
    checks = {
        "git SHA": report.get("git_sha") == candidate.get("git_sha"),
        "architecture": report.get("architecture") == "arm64",
        "product version": report.get("version") == candidate.get("product_version"),
        "runtime wave": report.get("runtime_wave") == EXPECTED_RUNTIME_WAVE,
        "candidate source digest": report.get("candidate_source_sha256") == candidate.get("candidate_source_sha256"),
        "candidate manifest digest": report.get("candidate_manifest_sha256") == manifest_sha,
        "source contract wave": report.get("source_contract_wave") == SOURCE_CONTRACT_WAVE,
        "source release state": report.get("source_release_state") == source_state,
        "source release tag": report.get("source_release_tag") == source_tag,
    }
    failed = [name for name, ok in checks.items() if not ok]
    _require(not failed, "Phase B candidate mismatch: " + ", ".join(failed))
    _require(report.get("release_authority") in {None, False}, "Phase B unexpectedly has release authority")
    _require(report.get("publication_authority") in {None, False}, "Phase B unexpectedly has publication authority")
    _require(report.get("production_ready") in {None, False}, "Phase B unexpectedly reports production-ready")
    _require(report.get("automatic_passed") is True, "Phase B automatic checks did not pass")
    _require(report.get("uat_passed") is True and report.get("overall") == "UAT_PASS", "Phase B is not UAT_PASS")

    manual = report.get("manual_steps") or []
    ids = {str(row.get("id")) for row in manual if isinstance(row, dict)}
    _require(ids == REQUIRED_PHASE_B_IDS and len(manual) == 12, "Phase B manual gate set drift")
    for row in manual:
        gate = str(row.get("id") or "unknown")
        _require(row.get("status") == "PASS", f"Phase B gate is not PASS: {gate}")
        _require(bool(str(row.get("note") or "").strip()), f"Phase B gate lacks concrete note: {gate}")
        _require(bool(str(row.get("recorded_at") or "").strip()), f"Phase B gate lacks recorded_at: {gate}")
    return {"required_gates": 12, "passed_gates": 12, "overall": "UAT_PASS", "updated_at": report.get("updated_at")}


def finalize(app: Path, phase_a_path: Path, phase_b_path: Path) -> dict[str, Any]:
    app, phase_a_path, phase_b_path = (p.expanduser().resolve() for p in (app, phase_a_path, phase_b_path))
    _require(app.is_dir(), f"app bundle missing: {app}")
    _require(phase_a_path.is_file(), f"Phase A evidence missing: {phase_a_path}")
    _require(phase_b_path.is_file(), f"Phase B evidence missing: {phase_b_path}")
    candidate, candidate_path, provenance, source_state, source_tag = _load_candidate(app)
    manifest_sha = _sha256_file(candidate_path)
    a = _phase_a(_load(phase_a_path), candidate)
    b = _phase_b(_load(phase_b_path), candidate, manifest_sha, source_state, source_tag)
    binding = {
        "git_sha": candidate.get("git_sha"), "product_version": candidate.get("product_version"),
        "architecture": "arm64", "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "candidate_guard_wave": EXPECTED_CANDIDATE_GUARD_WAVE,
        "certification_guard_wave": EXPECTED_CANDIDATE_GUARD_WAVE,
        "attestation_wave": ATTESTATION_WAVE, "source_contract_wave": SOURCE_CONTRACT_WAVE,
        "source_release_state": source_state, "source_release_tag": source_tag,
        "candidate_source_sha256": candidate.get("candidate_source_sha256"),
        "candidate_manifest_sha256": manifest_sha, "build_origin": candidate.get("build_origin"),
        "provenance_schema": provenance.get("schema"),
    }
    core = {
        "schema": ATTESTATION_SCHEMA, "binding": binding,
        "phase_a": {**a, "report_sha256": _sha256_file(phase_a_path)},
        "phase_b": {**b, "report_sha256": _sha256_file(phase_b_path)},
        "both_phases_passed": True, "release_authority": False,
        "publication_authority": False, "production_ready": False,
    }
    return {**core, "generated_at": datetime.now(timezone.utc).isoformat(), "attestation_sha256": _digest(core)}


def render_markdown(report: dict[str, Any]) -> str:
    b, a, p = report["binding"], report["phase_a"], report["phase_b"]
    return "\n".join([
        "# BINARIO Marketing IA · Combined Physical UAT Attestation", "",
        f"- Git SHA: `{b['git_sha']}`", f"- Version: `{b['product_version']}`",
        f"- Source release state: `{b['source_release_state']}`", f"- Prepared release tag: `{b['source_release_tag']}`",
        f"- Architecture: `{b['architecture']}`", f"- Runtime: `Wave {b['runtime_wave']}`",
        f"- Source contract: `Wave {b['source_contract_wave']}`",
        f"- Candidate source SHA-256: `{b['candidate_source_sha256']}`",
        f"- Candidate manifest SHA-256: `{b['candidate_manifest_sha256']}`",
        f"- Phase A: **PASS** · {a['passed_scenarios']}/{a['required_scenarios']} required scenarios",
        f"- Phase A required IDs: `{','.join(a['required_scenario_ids'])}`",
        f"- Phase A optional IDs: `{','.join(a['optional_scenario_ids'])}`",
        f"- Phase B: **PASS** · {p['passed_gates']}/{p['required_gates']} release gates",
        f"- Combined attestation SHA-256: `{report['attestation_sha256']}`",
        "- Release authority: **NO**", "- Publication authority: **NO**", "- Production ready: **NO**", "",
        "This attestation proves only that both physical UAT layers passed on the same trusted exact main candidate and same source release state.",
        "Only PREPARED_RELEASE evidence with exact SHA/source/tag/version binding may later satisfy a production release gate.", "",
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
    out = args.output.expanduser().resolve(); out.mkdir(parents=True, exist_ok=True)
    json_path = out / "combined-physical-uat-attestation.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "combined-physical-uat-attestation.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"both_phases_passed": True, "git_sha": report["binding"]["git_sha"], "source_release_state": report["binding"]["source_release_state"], "source_release_tag": report["binding"]["source_release_tag"], "source_contract_wave": report["binding"]["source_contract_wave"], "attestation_sha256": report["attestation_sha256"], "output": str(json_path), "release_authority": False}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
