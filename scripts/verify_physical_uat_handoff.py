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
SOURCE_CONTRACT_WAVE = 95
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _trusted_origin(payload: dict[str, Any]) -> bool:
    origin = payload.get("build_origin") if isinstance(payload.get("build_origin"), dict) else {}
    return bool(origin.get("event") == "push" and origin.get("ref") == "refs/heads/main" and origin.get("trusted_for_physical_uat") is True)


def _candidate_source_contract(payload: dict[str, Any]) -> tuple[str, str | None]:
    boundary = payload.get("release_boundary") if isinstance(payload.get("release_boundary"), dict) else {}
    version = str(payload.get("product_version") or "")
    state = payload.get("source_release_state") or boundary.get("source_release_state")
    ready = boundary.get("release_ready")
    tag = boundary.get("release_tag")
    if state is None and ready is False and tag is None:
        state = LOCKED_SOURCE
    _require(boundary.get("operational_authorization") in {None, False}, "candidate unexpectedly carries operational authority")
    _require(boundary.get("release_authority") in {None, False}, "candidate unexpectedly carries release authority")
    _require(boundary.get("publication_authority") in {None, False}, "candidate unexpectedly carries publication authority")
    _require(boundary.get("production_ready") is False, "candidate unexpectedly reports production-ready")
    if state == LOCKED_SOURCE:
        _require(ready is False and tag is None, "LOCKED_SOURCE candidate boundary drift")
    elif state == PREPARED_RELEASE:
        _require(ready is True and tag == f"v{version}", "PREPARED_RELEASE candidate tag/version mismatch")
        _require(".dev" not in version.lower() and "rc" not in version.lower(), "PREPARED_RELEASE candidate version is not stable")
    else:
        raise ValueError("candidate source release state is missing or invalid")
    return str(state), str(tag) if tag is not None else None


def verify(delivery_dir: Path, app: Path, *, expected_git_sha: str | None = None, require_physical_host: bool = False) -> dict[str, Any]:
    delivery_dir = delivery_dir.expanduser().resolve(); app = app.expanduser().resolve()
    _require(delivery_dir.is_dir(), f"delivery directory missing: {delivery_dir}")
    _require(app.is_dir(), f"app bundle missing: {app}")
    resources = app / "Contents" / "Resources"
    source = resources / "source"
    delivery_path = delivery_dir / "FULL_MAC_DELIVERY.json"
    external_candidate_path = delivery_dir / "PHYSICAL_UAT_CANDIDATE.json"
    internal_candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    provenance_path = resources / "BUILD_PROVENANCE.json"; readiness_path = resources / "RELEASE_READINESS.json"
    delivery = _json(delivery_path); external = _json(external_candidate_path); internal = _json(internal_candidate_path); provenance = _json(provenance_path); readiness = _json(readiness_path)

    _require(delivery.get("schema") == DELIVERY_SCHEMA, "unexpected delivery schema")
    _require(external.get("schema") == CANDIDATE_SCHEMA, "unexpected external candidate schema")
    _require(internal.get("schema") == CANDIDATE_SCHEMA, "unexpected embedded candidate schema")
    _require(provenance.get("schema") == PROVENANCE_SCHEMA, "unexpected build provenance schema")
    _require(readiness.get("schema") == READINESS_SCHEMA, "unexpected embedded readiness schema")

    trusted = _trusted_origin(delivery); role = PHYSICAL_ROLE if trusted else VALIDATION_ROLE
    _require(delivery.get("role") == role, "delivery role/build-origin mismatch")
    _require(delivery.get("physical_uat_eligible") is trusted, "delivery physical-UAT eligibility mismatch")
    source_contracts: list[tuple[str, str | None]] = []
    for label, payload in (("external candidate", external), ("embedded candidate", internal)):
        _require(payload.get("role") == role, f"{label} role mismatch")
        _require(_trusted_origin(payload) is trusted, f"{label} build-origin trust mismatch")
        _require((payload.get("physical_uat") or {}).get("eligible_build_origin") is trusted, f"{label} origin eligibility mismatch")
        _require(payload.get("build_origin") == delivery.get("build_origin"), f"{label} build origin differs from delivery")
        _require(payload.get("source_contract_wave") == SOURCE_CONTRACT_WAVE, f"{label} source contract wave drift")
        source_contracts.append(_candidate_source_contract(payload))
    _require(source_contracts[0] == source_contracts[1], "external/embedded candidate source contract mismatch")
    source_state, source_tag = source_contracts[0]
    _require(delivery.get("source_release_state") in {None, source_state}, "delivery source release state mismatch")
    _require(delivery.get("source_release_tag") == source_tag, "delivery source release tag mismatch")
    _require(readiness.get("source_release_state") in {None, source_state}, "embedded readiness source release state mismatch")
    _require(readiness.get("release_tag") == source_tag, "embedded readiness release tag mismatch")

    git_sha = str(delivery.get("git_sha") or "")
    _require(len(git_sha) == 40, "delivery git SHA is missing or malformed")
    if expected_git_sha is not None:
        _require(git_sha == expected_git_sha, f"delivery git SHA mismatch: {git_sha} != {expected_git_sha}")
    for label, value in (("external candidate", external.get("git_sha")), ("embedded candidate", internal.get("git_sha")), ("build provenance", provenance.get("git_sha")), ("embedded readiness", readiness.get("git_sha"))):
        _require(value == git_sha, f"{label} git SHA does not match delivery")

    for label, payload in (("delivery", delivery), ("external candidate", external), ("embedded candidate", internal), ("build provenance", provenance), ("embedded readiness", readiness)):
        _require(payload.get("architecture") == EXPECTED_ARCH, f"{label} is not arm64")
    _require(delivery.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "delivery runtime wave drift")
    _require(external.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "external runtime wave drift")
    _require(internal.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "embedded runtime wave drift")
    for label, payload in (("delivery", delivery), ("external candidate", external), ("embedded candidate", internal)):
        _require(payload.get("certification_guard_wave") == EXPECTED_GUARD_WAVE, f"{label} certification guard drift")
    _require(delivery.get("operator_handoff_wave") == EXPECTED_HANDOFF_WAVE, "operator handoff wave drift")
    _require(delivery.get("source_contract_wave") == SOURCE_CONTRACT_WAVE, "source contract wave drift")

    source_sha = str(delivery.get("candidate_source_sha256") or "")
    _require(len(source_sha) == 64, "delivery candidate source SHA-256 malformed")
    _require(external.get("candidate_source_sha256") == source_sha, "external candidate source digest mismatch")
    _require(internal.get("candidate_source_sha256") == source_sha, "embedded candidate source digest mismatch")
    actual_source_sha = _source_digest(source)
    _require(actual_source_sha == source_sha, "candidate source digest does not match extracted app")
    expected_manifest_sha = str(delivery.get("candidate_manifest_sha256") or "")
    _require(_sha256(internal_candidate_path) == expected_manifest_sha, "embedded candidate manifest digest mismatch")
    _require(_sha256(external_candidate_path) == expected_manifest_sha, "external candidate manifest digest mismatch")

    artifact_name = str(delivery.get("artifact") or ""); _require(artifact_name.startswith("Binario-Marketing-IA-PHYSICAL-UAT-arm64-"), "unexpected artifact identity")
    artifact_path = delivery_dir / artifact_name; _require(artifact_path.is_file(), f"candidate ZIP missing: {artifact_path}")
    artifact_sha = _sha256(artifact_path); _require(artifact_sha == delivery.get("artifact_sha256"), "candidate ZIP SHA-256 mismatch")
    checksum_path = delivery_dir / f"{artifact_name}.sha256"; _require(checksum_path.is_file(), "candidate checksum file missing")
    _require(checksum_path.read_text(encoding="utf-8").strip() == f"{artifact_sha}  {artifact_name}", "candidate checksum sidecar mismatch")

    helper_contract = [("PHYSICAL_UAT_HANDOFF_VERIFY.py", "handoff_verifier_sha256"), ("START_PHYSICAL_UAT.command", "start_command_sha256"), ("RECORD_RELEASE_UAT.command", "record_command_sha256"), ("PHYSICAL_UAT_OPERATOR.md", "operator_guide_sha256")]
    combined_wave = delivery.get("combined_attestation_wave")
    if combined_wave is not None:
        _require(combined_wave == COMBINED_ATTESTATION_WAVE, "combined attestation wave drift")
        _require(delivery.get("combined_attestation_required_before_release_transport") is True, "combined attestation release-transport boundary missing")
        helper_contract.extend([("FINALIZE_PHYSICAL_UAT.py", "combined_finalizer_sha256"), ("FINALIZE_PHYSICAL_UAT.command", "finalize_command_sha256")])
    helper_hashes: dict[str, str] = {}
    for filename, field in helper_contract:
        helper = delivery_dir / filename; _require(helper.is_file(), f"operator handoff helper missing: {filename}")
        actual = _sha256(helper); _require(actual == delivery.get(field), f"operator handoff helper digest mismatch: {filename}"); helper_hashes[filename] = actual

    _require(delivery.get("physical_product_uat_required") is True, "in-app physical product UAT requirement missing")
    _require(delivery.get("release_operational_uat_required") is True, "release operational UAT requirement missing")
    _require(delivery.get("release_ready") is False, "handoff delivery must not itself be release-ready")
    _require(delivery.get("release_tag") is None, "handoff delivery must not itself carry a release tag")
    _require(delivery.get("operational_authorization") in {None, False}, "handoff delivery unexpectedly has operational authority")
    _require(delivery.get("release_authority") in {None, False}, "handoff delivery unexpectedly has release authority")
    _require(delivery.get("publication_authority") in {None, False}, "handoff delivery unexpectedly has publication authority")
    _require(delivery.get("production_ready") is False, "delivery unexpectedly production-ready")
    _require(delivery.get("automatic_uat_pass") is False, "delivery unexpectedly allows automatic UAT pass")

    system = platform.system(); machine = platform.machine().lower(); is_ci = str(os.environ.get("GITHUB_ACTIONS") or "").lower() == "true" or str(os.environ.get("CI") or "").lower() == "true"; physical_host = system == "Darwin" and machine == "arm64" and not is_ci
    if require_physical_host:
        _require(physical_host, f"physical UAT requires real non-CI Darwin arm64 host; got {system}/{machine}/CI={is_ci}")
        _require(trusted, "physical UAT requires a trusted push build from canonical main; validation artifacts are forbidden")
        _require(role == PHYSICAL_ROLE, "physical UAT requires PHYSICAL_UAT_CANDIDATE_ONLY role")

    return {
        "schema": "binario.marketing.physical-uat-handoff-verification.v3", "git_sha": git_sha, "role": role,
        "build_origin": delivery.get("build_origin"), "physical_uat_eligible": trusted, "architecture": EXPECTED_ARCH,
        "runtime_wave": EXPECTED_RUNTIME_WAVE, "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "operator_handoff_wave": EXPECTED_HANDOFF_WAVE, "combined_attestation_wave": combined_wave,
        "source_contract_wave": delivery.get("source_contract_wave"), "source_release_state": source_state, "source_release_tag": source_tag,
        "candidate_source_sha256": source_sha, "actual_candidate_source_sha256": actual_source_sha,
        "candidate_manifest_sha256": expected_manifest_sha,
        "artifact": artifact_name, "artifact_sha256": artifact_sha, "operator_helpers": helper_hashes,
        "host": {"system": system, "machine": machine, "is_ci": is_ci, "physical_gate_eligible": physical_host},
        "physical_product_uat_required": True, "release_operational_uat_required": True,
        "ready_for_operator_uat": physical_host and trusted, "automatic_uat_pass": False,
        "operational_authorization": False, "release_authority": False, "publication_authority": False, "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a W84/W85/W95/W97 UAT delivery; physical start additionally requires trusted main origin and real arm64 host."); parser.add_argument("--delivery-dir", type=Path, required=True); parser.add_argument("--app", type=Path, required=True); parser.add_argument("--expected-git-sha"); parser.add_argument("--require-physical-host", action="store_true"); args = parser.parse_args()
    try:
        report = verify(args.delivery_dir, args.app, expected_git_sha=args.expected_git_sha, require_physical_host=args.require_physical_host)
    except ValueError as exc:
        raise SystemExit(f"PHYSICAL UAT HANDOFF BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
