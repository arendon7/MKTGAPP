#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.combined-physical-uat-attestation.v1"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 84
EXPECTED_ARCHITECTURE = "arm64"


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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(path: Path, *, expected_git_sha: str | None = None) -> dict[str, Any]:
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
    _require(binding.get("certification_guard_wave") == EXPECTED_GUARD_WAVE, "combined UAT certification guard drift")
    source_sha = str(binding.get("candidate_source_sha256") or "")
    manifest_sha = str(binding.get("candidate_manifest_sha256") or "")
    _require(len(source_sha) == 64, "combined UAT candidate source SHA-256 missing or malformed")
    _require(len(manifest_sha) == 64, "combined UAT candidate manifest SHA-256 missing or malformed")

    phase_a = data.get("phase_a") or {}
    phase_b = data.get("phase_b") or {}
    _require(isinstance(phase_a, dict) and isinstance(phase_b, dict), "combined UAT phase summaries missing")
    required_scenarios = int(phase_a.get("required_scenarios") or 0)
    passed_scenarios = int(phase_a.get("passed_scenarios") or 0)
    required_gates = int(phase_b.get("required_gates") or 0)
    passed_gates = int(phase_b.get("passed_gates") or 0)
    _require(required_scenarios > 0 and passed_scenarios == required_scenarios, "combined UAT Phase A is not fully passed")
    _require(required_gates == 12 and passed_gates == required_gates, "combined UAT Phase B is not 12/12 PASS")
    _require(phase_b.get("overall") == "UAT_PASS", "combined UAT Phase B overall result is not UAT_PASS")
    _require(data.get("both_phases_passed") is True, "combined UAT both_phases_passed is not true")
    _require(data.get("release_authority") is False, "combined UAT must not carry release authority")
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
        "candidate_source_sha256": source_sha,
        "candidate_manifest_sha256": manifest_sha,
        "phase_a_required": required_scenarios,
        "phase_a_passed": passed_scenarios,
        "phase_b_required": required_gates,
        "phase_b_passed": passed_gates,
        "attestation_sha256": expected_sha,
        "both_phases_passed": True,
        "release_authority": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a sanitized W85 combined physical-UAT attestation.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-git-sha")
    args = parser.parse_args()
    try:
        report = verify(args.evidence, expected_git_sha=args.expected_git_sha)
    except ValueError as exc:
        raise SystemExit(f"COMBINED UAT ATTESTATION BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
