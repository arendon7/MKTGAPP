#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.combined-physical-uat-attestation.v1"
W97_INTEGRITY_SCHEMA = "binario.marketing.physical-uat-final-integrity.v1"
W97_HANDOFF_SCHEMA = "binario.marketing.physical-uat-handoff-verification.v3"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 84
EXPECTED_SOURCE_CONTRACT_WAVE = 95
EXPECTED_ARCHITECTURE = "arm64"
EXPECTED_REQUIRED_PHASE_A_IDS = {
    "company-switch", "inbox-to-crm", "pipeline-followup",
    "campaign-execution", "results-decision",
}
EXPECTED_OPTIONAL_PHASE_A_IDS = {"optional-ai"}
LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid combined UAT attestation: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("combined UAT attestation must be a JSON object")
    return data


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _handoff_report_sha256(payload: dict[str, Any]) -> str:
    """Reconstruct the exact verifier CLI JSON bytes written by FINALIZE_PHYSICAL_UAT.command."""
    raw = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _source_contract(binding: dict[str, Any]) -> tuple[str, str | None, int | None]:
    version = str(binding.get("product_version") or "")
    state = binding.get("source_release_state")
    tag = binding.get("source_release_tag")
    wave = binding.get("source_contract_wave")
    # Pre-W95 sanitized attestations remain diagnosable as LOCKED_SOURCE only.
    # They can never satisfy a PREPARED_RELEASE production gate.
    if state is None and tag is None:
        state = LOCKED_SOURCE
    if state == LOCKED_SOURCE:
        _require(tag is None, "LOCKED_SOURCE combined UAT cannot carry a release tag")
        _require(wave in {None, EXPECTED_SOURCE_CONTRACT_WAVE}, "LOCKED_SOURCE combined UAT source contract wave drift")
    elif state == PREPARED_RELEASE:
        _require(wave == EXPECTED_SOURCE_CONTRACT_WAVE, "PREPARED_RELEASE combined UAT must carry the W95 source contract")
        _require(tag == f"v{version}", "PREPARED_RELEASE combined UAT tag/version mismatch")
        _require(".dev" not in version.lower() and "rc" not in version.lower(), "PREPARED_RELEASE combined UAT version is not stable")
    else:
        raise ValueError("combined UAT source release state is missing or invalid")
    return str(state), str(tag) if tag is not None else None, int(wave) if wave is not None else None


def _w97_integrity(data: dict[str, Any], binding: dict[str, Any], source_state: str) -> dict[str, Any] | None:
    integrity = data.get("w97_integrity")
    if source_state != PREPARED_RELEASE:
        if integrity is None:
            return None
        _require(isinstance(integrity, dict), "W97 final integrity must be a JSON object")
        return integrity

    _require(isinstance(integrity, dict), "PREPARED_RELEASE combined UAT requires W97 final integrity")
    _require(integrity.get("schema") == W97_INTEGRITY_SCHEMA, "W97 final integrity schema drift")
    handoff_sha = str(integrity.get("handoff_verification_sha256") or "")
    _require(len(handoff_sha) == 64, "W97 final handoff verification SHA-256 missing or malformed")
    _require(integrity.get("bundle_signature_verified") is True, "W97 final bundle signature was not reverified")
    _require(integrity.get("source_digest_reverified") is True, "W97 final source digest was not reverified")
    _require(integrity.get("physical_host_reverified") is True, "W97 final physical host was not reverified")
    _require(integrity.get("codesign_requirement") == ["--deep", "--strict"], "W97 codesign requirement drift")

    handoff = integrity.get("handoff_verification")
    _require(isinstance(handoff, dict), "W97 embedded final handoff verification missing")
    _require(
        _handoff_report_sha256(handoff) == handoff_sha,
        "W97 final handoff verification SHA-256 mismatch",
    )
    _require(handoff.get("schema") == W97_HANDOFF_SCHEMA, "W97 embedded handoff schema drift")
    _require(handoff.get("role") == "PHYSICAL_UAT_CANDIDATE_ONLY", "W97 embedded handoff is not the physical candidate")
    _require(handoff.get("physical_uat_eligible") is True, "W97 embedded handoff is not physically eligible")
    _require(handoff.get("git_sha") == binding.get("git_sha"), "W97 embedded handoff git SHA mismatch")
    _require(handoff.get("architecture") == binding.get("architecture") == EXPECTED_ARCHITECTURE, "W97 embedded handoff architecture mismatch")
    _require(handoff.get("runtime_wave") == binding.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "W97 embedded handoff runtime wave mismatch")
    _require(handoff.get("source_contract_wave") == binding.get("source_contract_wave") == EXPECTED_SOURCE_CONTRACT_WAVE, "W97 embedded handoff source contract mismatch")
    _require(handoff.get("source_release_state") == binding.get("source_release_state") == PREPARED_RELEASE, "W97 embedded handoff source state mismatch")
    _require(handoff.get("source_release_tag") == binding.get("source_release_tag"), "W97 embedded handoff release tag mismatch")
    _require(handoff.get("candidate_source_sha256") == binding.get("candidate_source_sha256"), "W97 embedded handoff source digest mismatch")
    _require(handoff.get("actual_candidate_source_sha256") == binding.get("candidate_source_sha256"), "W97 embedded extracted source digest mismatch")
    _require(handoff.get("candidate_manifest_sha256") == binding.get("candidate_manifest_sha256"), "W97 embedded handoff manifest digest mismatch")
    host = handoff.get("host") or {}
    _require(isinstance(host, dict), "W97 embedded handoff host missing")
    _require(host.get("system") == "Darwin", "W97 embedded handoff host is not Darwin")
    _require(str(host.get("machine") or "").lower() == "arm64", "W97 embedded handoff host is not arm64")
    _require(host.get("is_ci") is False, "W97 embedded handoff cannot come from CI")
    _require(host.get("physical_gate_eligible") is True, "W97 embedded handoff host is not physical-gate eligible")
    return integrity


def _phase_a_contract(phase_a: dict[str, Any], source_state: str) -> tuple[int, int, list[str] | None, list[str] | None]:
    required_scenarios = int(phase_a.get("required_scenarios") or 0)
    passed_scenarios = int(phase_a.get("passed_scenarios") or 0)
    required_ids_raw = phase_a.get("required_scenario_ids")
    optional_ids_raw = phase_a.get("optional_scenario_ids")

    if source_state == PREPARED_RELEASE:
        _require(required_scenarios == len(EXPECTED_REQUIRED_PHASE_A_IDS), "combined UAT Phase A required scenario count drift")
        _require(passed_scenarios == required_scenarios, "combined UAT Phase A is not fully passed")
        _require(isinstance(required_ids_raw, list), "PREPARED_RELEASE combined UAT Phase A required IDs missing")
        _require(isinstance(optional_ids_raw, list), "PREPARED_RELEASE combined UAT Phase A optional IDs missing")
        required_ids = [str(value) for value in required_ids_raw]
        optional_ids = [str(value) for value in optional_ids_raw]
        _require(len(required_ids) == len(EXPECTED_REQUIRED_PHASE_A_IDS), "combined UAT Phase A required ID count drift")
        _require(len(set(required_ids)) == len(required_ids), "combined UAT Phase A required IDs contain duplicates")
        _require(set(required_ids) == EXPECTED_REQUIRED_PHASE_A_IDS, "combined UAT Phase A required ID set drift")
        _require(len(optional_ids) == len(EXPECTED_OPTIONAL_PHASE_A_IDS), "combined UAT Phase A optional ID count drift")
        _require(len(set(optional_ids)) == len(optional_ids), "combined UAT Phase A optional IDs contain duplicates")
        _require(set(optional_ids) == EXPECTED_OPTIONAL_PHASE_A_IDS, "combined UAT Phase A optional ID set drift")
        return required_scenarios, passed_scenarios, required_ids, optional_ids

    _require(required_scenarios > 0 and passed_scenarios == required_scenarios, "combined UAT Phase A is not fully passed")
    return required_scenarios, passed_scenarios, None, None


def verify(
    path: Path,
    *,
    expected_git_sha: str | None = None,
    expected_source_release_state: str | None = None,
    expected_release_tag: str | None = None,
) -> dict[str, Any]:
    path = path.expanduser().resolve()
    _require(path.is_file(), f"combined UAT attestation missing: {path}")
    data = _load(path)
    _require(data.get("schema") == SCHEMA, "unexpected combined UAT attestation schema")

    binding = data.get("binding") or {}
    _require(isinstance(binding, dict), "combined UAT binding missing")
    git_sha = str(binding.get("git_sha") or "")
    _require(len(git_sha) == 40, "combined UAT git SHA is missing or malformed")
    if expected_git_sha is not None:
        _require(git_sha == expected_git_sha, f"combined UAT git SHA mismatch: {git_sha} != {expected_git_sha}")
    _require(binding.get("architecture") == EXPECTED_ARCHITECTURE, "combined UAT physical architecture must be arm64")
    _require(binding.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "combined UAT runtime wave drift")
    certification_guard = binding.get("certification_guard_wave")
    candidate_guard = binding.get("candidate_guard_wave")
    if certification_guard is not None and candidate_guard is not None:
        _require(certification_guard == candidate_guard, "combined UAT guard aliases diverge")
    guard = certification_guard if certification_guard is not None else candidate_guard
    _require(guard == EXPECTED_GUARD_WAVE, "combined UAT certification guard drift")
    source_state, source_tag, source_contract_wave = _source_contract(binding)
    if expected_source_release_state is not None:
        _require(source_state == expected_source_release_state, f"combined UAT source release state mismatch: {source_state} != {expected_source_release_state}")
    if expected_release_tag is not None:
        _require(source_tag == expected_release_tag, f"combined UAT release tag mismatch: {source_tag} != {expected_release_tag}")
    if expected_source_release_state == PREPARED_RELEASE:
        _require(source_contract_wave == EXPECTED_SOURCE_CONTRACT_WAVE, "production-bound UAT is not W95 PREPARED_RELEASE evidence")
    source_sha = str(binding.get("candidate_source_sha256") or "")
    manifest_sha = str(binding.get("candidate_manifest_sha256") or "")
    _require(len(source_sha) == 64, "combined UAT candidate source SHA-256 missing or malformed")
    _require(len(manifest_sha) == 64, "combined UAT candidate manifest SHA-256 missing or malformed")
    w97_integrity = _w97_integrity(data, binding, source_state)

    phase_a = data.get("phase_a") or {}
    phase_b = data.get("phase_b") or {}
    _require(isinstance(phase_a, dict) and isinstance(phase_b, dict), "combined UAT phase summaries missing")
    required_scenarios, passed_scenarios, phase_a_required_ids, phase_a_optional_ids = _phase_a_contract(phase_a, source_state)
    required_gates = int(phase_b.get("required_gates") or 0)
    passed_gates = int(phase_b.get("passed_gates") or 0)
    _require(required_gates == 12 and passed_gates == required_gates, "combined UAT Phase B is not 12/12 PASS")
    _require(phase_b.get("overall") == "UAT_PASS", "combined UAT Phase B overall result is not UAT_PASS")
    _require(data.get("both_phases_passed") is True, "combined UAT both_phases_passed is not true")
    _require(data.get("release_authority") is False, "combined UAT must not carry release authority")
    _require(data.get("publication_authority") in {None, False}, "combined UAT must not carry publication authority")
    _require(data.get("production_ready") is False, "combined UAT must not claim production readiness")

    expected_sha = str(data.get("attestation_sha256") or "")
    _require(len(expected_sha) == 64, "combined UAT attestation SHA-256 missing or malformed")
    core = dict(data)
    core.pop("generated_at", None)
    core.pop("attestation_sha256", None)
    actual_sha = _digest(core)
    _require(actual_sha == expected_sha, "combined UAT attestation digest mismatch")

    return {
        "schema": SCHEMA,
        "git_sha": git_sha,
        "architecture": EXPECTED_ARCHITECTURE,
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "source_contract_wave": source_contract_wave,
        "source_release_state": source_state,
        "source_release_tag": source_tag,
        "candidate_source_sha256": source_sha,
        "candidate_manifest_sha256": manifest_sha,
        "phase_a_required": required_scenarios,
        "phase_a_passed": passed_scenarios,
        "phase_a_required_ids": phase_a_required_ids,
        "phase_a_optional_ids": phase_a_optional_ids,
        "phase_b_required": required_gates,
        "phase_b_passed": passed_gates,
        "attestation_sha256": expected_sha,
        "w97_integrity_required": source_state == PREPARED_RELEASE,
        "w97_integrity_verified": isinstance(w97_integrity, dict) if source_state == PREPARED_RELEASE else w97_integrity is not None,
        "w97_handoff_verification_sha256": (w97_integrity or {}).get("handoff_verification_sha256"),
        "w98_handoff_seal_verified": source_state != PREPARED_RELEASE or isinstance(w97_integrity, dict),
        "both_phases_passed": True,
        "release_authority": False,
        "publication_authority": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a sanitized W85/W95/W97/W98 combined physical-UAT attestation.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-git-sha")
    parser.add_argument("--expected-source-release-state", choices=(LOCKED_SOURCE, PREPARED_RELEASE))
    parser.add_argument("--expected-release-tag")
    args = parser.parse_args()
    try:
        report = verify(
            args.evidence,
            expected_git_sha=args.expected_git_sha,
            expected_source_release_state=args.expected_source_release_state,
            expected_release_tag=args.expected_release_tag,
        )
    except ValueError as exc:
        raise SystemExit(f"COMBINED UAT ATTESTATION BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
