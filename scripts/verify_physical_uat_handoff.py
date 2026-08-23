#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v3"
CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
READINESS_SCHEMA = "binario.marketing.release-readiness.v1"
PROVENANCE_SCHEMA = "binario.marketing.full-mac-build.v4"
PHYSICAL_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"
VALIDATION_ROLE = "VALIDATION_BUILD_ONLY"
EXPECTED_ARCH = "arm64"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 84
EXPECTED_HANDOFF_WAVE = 84
COMBINED_ATTESTATION_WAVE = 85
PREPARED_RELEASE_CONTRACT_WAVE = 91
LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"


def _json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _development_version(version: str) -> bool:
    value = str(version or "").lower()
    return not value or any(token in value for token in (".dev", "-dev", "alpha", "beta", "rc"))


def _normalize_release_contract(payload: dict[str, Any], version: str, *, delivery: bool = False) -> dict[str, Any]:
    raw = payload.get("source_release_contract") if delivery else payload.get("release_boundary")
    raw = raw if isinstance(raw, dict) else {}
    release_ready = raw.get("release_ready") is True if raw else payload.get("release_ready") is True
    release_tag = raw.get("release_tag") if raw else payload.get("release_tag")
    mode = raw.get("mode") if raw else None
    if mode is None:
        mode = PREPARED_RELEASE if release_ready else LOCKED_SOURCE
    if mode == LOCKED_SOURCE:
        _require(not release_ready and release_tag is None, "locked source release contract is inconsistent")
    elif mode == PREPARED_RELEASE:
        _require(release_ready, "prepared release contract must set release_ready")
        _require(not _development_version(version), "prepared release contract cannot use development/RC version")
        _require(release_tag == f"v{version}", "prepared release contract tag/version mismatch")
    else:
        raise ValueError(f"unknown source release contract mode: {mode}")
    if raw:
        _require(raw.get("production_ready") is not True, "source release contract cannot claim production readiness")
        _require(raw.get("release_authority") not in {True}, "source release contract cannot claim release authority")
        _require(raw.get("operational_authorization") not in {True}, "source release contract cannot claim operational authorization")
    _require(payload.get("production_ready") is not True, "delivery/candidate unexpectedly production-ready")
    _require(payload.get("release_authority") not in {True}, "delivery/candidate unexpectedly has release authority")
    _require(payload.get("operational_authorization") not in {True}, "delivery/candidate unexpectedly has operational authorization")
    return {
        "mode": mode,
        "version": version,
        "release_ready": release_ready,
        "release_tag": release_tag,
        "production_ready": False,
        "release_authority": False,
        "operational_authorization": False,
    }


def _trusted_origin(payload: dict[str, Any]) -> bool:
    origin = payload.get("build_origin") if isinstance(payload.get("build_origin"), dict) else {}
    # refs/tags/v* are W88 source-equivalent distribution rebuilds, never exact physical candidates.
    return bool(
        origin.get("event") == "push"
        and origin.get("ref") == "refs/heads/main"
        and origin.get("trusted_for_physical_uat") is True
    )


def verify(delivery_dir: Path, app: Path, *, expected_git_sha: str | None = None, require_physical_host: bool = False) -> dict[str, Any]:
    delivery_dir = delivery_dir.expanduser().resolve()
    app = app.expanduser().resolve()
    _require(delivery_dir.is_dir(), f"delivery directory missing: {delivery_dir}")
    _require(app.is_dir(), f"app bundle missing: {app}")
    resources = app / "Contents" / "Resources"
    delivery_path = delivery_dir / "FULL_MAC_DELIVERY.json"
    external_candidate_path = delivery_dir / "PHYSICAL_UAT_CANDIDATE.json"
    internal_candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    provenance_path = resources / "BUILD_PROVENANCE.json"
    readiness_path = resources / "RELEASE_READINESS.json"
    delivery = _json(delivery_path)
    external = _json(external_candidate_path)
    internal = _json(internal_candidate_path)
    provenance = _json(provenance_path)
    readiness = _json(readiness_path)

    _require(delivery.get("schema") == DELIVERY_SCHEMA, "unexpected delivery schema")
    _require(external.get("schema") == CANDIDATE_SCHEMA, "unexpected external candidate schema")
    _require(internal.get("schema") == CANDIDATE_SCHEMA, "unexpected embedded candidate schema")
    _require(provenance.get("schema") == PROVENANCE_SCHEMA, "unexpected build provenance schema")
    _require(readiness.get("schema") == READINESS_SCHEMA, "unexpected embedded readiness schema")

    trusted = _trusted_origin(delivery)
    role = PHYSICAL_ROLE if trusted else VALIDATION_ROLE
    _require(delivery.get("role") == role, "delivery role/build-origin mismatch")
    _require(delivery.get("physical_uat_eligible") is trusted, "delivery physical-UAT eligibility mismatch")
    for label, payload in (("external candidate", external), ("embedded candidate", internal)):
        _require(payload.get("role") == role, f"{label} role mismatch")
        _require(_trusted_origin(payload) is trusted, f"{label} build-origin trust mismatch")
        _require((payload.get("physical_uat") or {}).get("eligible_build_origin") is trusted, f"{label} origin eligibility mismatch")
        _require(payload.get("build_origin") == delivery.get("build_origin"), f"{label} build origin differs from delivery")

    git_sha = str(delivery.get("git_sha") or "")
    _require(len(git_sha) == 40, "delivery git SHA is missing or malformed")
    if expected_git_sha is not None:
        _require(git_sha == expected_git_sha, f"delivery git SHA mismatch: {git_sha} != {expected_git_sha}")
    for label, value in (
        ("external candidate", external.get("git_sha")),
        ("embedded candidate", internal.get("git_sha")),
        ("build provenance", provenance.get("git_sha")),
        ("embedded readiness", readiness.get("git_sha")),
    ):
        _require(value == git_sha, f"{label} git SHA does not match delivery")

    for label, payload in (
        ("delivery", delivery),
        ("external candidate", external),
        ("embedded candidate", internal),
        ("build provenance", provenance),
        ("embedded readiness", readiness),
    ):
        _require(payload.get("architecture") == EXPECTED_ARCH, f"{label} is not arm64")
    _require(delivery.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "delivery runtime wave drift")
    _require(external.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "external runtime wave drift")
    _require(internal.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "embedded runtime wave drift")
    for label, payload in (("delivery", delivery), ("external candidate", external), ("embedded candidate", internal)):
        _require(payload.get("certification_guard_wave") == EXPECTED_GUARD_WAVE, f"{label} certification guard drift")
    _require(delivery.get("operator_handoff_wave") == EXPECTED_HANDOFF_WAVE, "operator handoff wave drift")
    if delivery.get("prepared_release_contract_wave") is not None:
        _require(delivery.get("prepared_release_contract_wave") == PREPARED_RELEASE_CONTRACT_WAVE, "prepared release contract wave drift")

    product_version = str(delivery.get("product_version") or external.get("product_version") or provenance.get("product_version") or "")
    external_contract = _normalize_release_contract(external, product_version)
    internal_contract = _normalize_release_contract(internal, product_version)
    delivery_contract = _normalize_release_contract(delivery, product_version, delivery=True)
    _require(external_contract == internal_contract == delivery_contract, "source release contract differs across candidate delivery")
    if "release_ready_flag" in readiness:
        _require(bool(readiness.get("release_ready_flag")) == delivery_contract["release_ready"], "embedded readiness release flag differs from candidate contract")
    if "release_tag" in readiness:
        _require(readiness.get("release_tag") == delivery_contract["release_tag"], "embedded readiness release tag differs from candidate contract")
    _require(readiness.get("production_ready") is not True, "embedded readiness unexpectedly production-ready")

    source_sha = str(delivery.get("candidate_source_sha256") or "")
    _require(len(source_sha) == 64, "delivery candidate source SHA-256 malformed")
    _require(external.get("candidate_source_sha256") == source_sha, "external candidate source digest mismatch")
    _require(internal.get("candidate_source_sha256") == source_sha, "embedded candidate source digest mismatch")
    expected_manifest_sha = str(delivery.get("candidate_manifest_sha256") or "")
    _require(_sha256(internal_candidate_path) == expected_manifest_sha, "embedded candidate manifest digest mismatch")
    _require(_sha256(external_candidate_path) == expected_manifest_sha, "external candidate manifest digest mismatch")

    artifact_name = str(delivery.get("artifact") or "")
    _require(artifact_name.startswith("Binario-Marketing-IA-PHYSICAL-UAT-arm64-"), "unexpected artifact identity")
    artifact_path = delivery_dir / artifact_name
    _require(artifact_path.is_file(), f"candidate ZIP missing: {artifact_path}")
    artifact_sha = _sha256(artifact_path)
    _require(artifact_sha == delivery.get("artifact_sha256"), "candidate ZIP SHA-256 mismatch")
    checksum_path = delivery_dir / f"{artifact_name}.sha256"
    _require(checksum_path.is_file(), "candidate checksum file missing")
    _require(checksum_path.read_text(encoding="utf-8").strip() == f"{artifact_sha}  {artifact_name}", "candidate checksum sidecar mismatch")

    helper_contract = [
        ("PHYSICAL_UAT_HANDOFF_VERIFY.py", "handoff_verifier_sha256"),
        ("START_PHYSICAL_UAT.command", "start_command_sha256"),
        ("RECORD_RELEASE_UAT.command", "record_command_sha256"),
        ("PHYSICAL_UAT_OPERATOR.md", "operator_guide_sha256"),
    ]
    combined_wave = delivery.get("combined_attestation_wave")
    if combined_wave is not None:
        _require(combined_wave == COMBINED_ATTESTATION_WAVE, "combined attestation wave drift")
        _require(delivery.get("combined_attestation_required_before_release_transport") is True, "combined attestation release-transport boundary missing")
        helper_contract.extend([
            ("FINALIZE_PHYSICAL_UAT.py", "combined_finalizer_sha256"),
            ("FINALIZE_PHYSICAL_UAT.command", "finalize_command_sha256"),
        ])
    helper_hashes: dict[str, str] = {}
    for filename, field in helper_contract:
        helper = delivery_dir / filename
        _require(helper.is_file(), f"operator handoff helper missing: {filename}")
        actual = _sha256(helper)
        _require(actual == delivery.get(field), f"operator handoff helper digest mismatch: {filename}")
        helper_hashes[filename] = actual

    _require(delivery.get("physical_product_uat_required") is True, "in-app physical product UAT requirement missing")
    _require(delivery.get("release_operational_uat_required") is True, "release operational UAT requirement missing")
    _require(delivery.get("production_ready") is False, "delivery unexpectedly production-ready")
    _require(delivery.get("automatic_uat_pass") is False, "delivery unexpectedly allows automatic UAT pass")

    system = platform.system()
    machine = platform.machine().lower()
    is_ci = str(os.environ.get("GITHUB_ACTIONS") or "").lower() == "true" or str(os.environ.get("CI") or "").lower() == "true"
    physical_host = system == "Darwin" and machine == "arm64" and not is_ci
    if require_physical_host:
        _require(physical_host, f"physical UAT requires real non-CI Darwin arm64 host; got {system}/{machine}/CI={is_ci}")
        _require(trusted, "physical UAT requires a trusted push build from main; validation and tag artifacts are forbidden")
        _require(role == PHYSICAL_ROLE, "physical UAT requires PHYSICAL_UAT_CANDIDATE_ONLY role")

    return {
        "schema": "binario.marketing.physical-uat-handoff-verification.v3",
        "git_sha": git_sha,
        "role": role,
        "build_origin": delivery.get("build_origin"),
        "physical_uat_eligible": trusted,
        "architecture": EXPECTED_ARCH,
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "operator_handoff_wave": EXPECTED_HANDOFF_WAVE,
        "combined_attestation_wave": combined_wave,
        "prepared_release_contract_wave": delivery.get("prepared_release_contract_wave"),
        "source_release_contract": delivery_contract,
        "candidate_source_sha256": source_sha,
        "candidate_manifest_sha256": expected_manifest_sha,
        "artifact": artifact_name,
        "artifact_sha256": artifact_sha,
        "operator_helpers": helper_hashes,
        "host": {"system": system, "machine": machine, "is_ci": is_ci, "physical_gate_eligible": physical_host},
        "physical_product_uat_required": True,
        "release_operational_uat_required": True,
        "ready_for_operator_uat": physical_host and trusted,
        "automatic_uat_pass": False,
        "operational_authorization": False,
        "release_authority": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a physical-UAT delivery; physical start requires exact main-origin arm64 build.")
    parser.add_argument("--delivery-dir", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--expected-git-sha")
    parser.add_argument("--require-physical-host", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(args.delivery_dir, args.app, expected_git_sha=args.expected_git_sha, require_physical_host=args.require_physical_host)
    except ValueError as exc:
        raise SystemExit(f"PHYSICAL UAT HANDOFF BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
