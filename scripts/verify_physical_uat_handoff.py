#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from pathlib import Path
from typing import Any

DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v2"
CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
READINESS_SCHEMA = "binario.marketing.release-readiness.v1"
PROVENANCE_SCHEMA = "binario.marketing.full-mac-build.v4"
EXPECTED_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"
EXPECTED_ARCH = "arm64"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 81


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


def verify(
    delivery_dir: Path,
    app: Path,
    *,
    expected_git_sha: str | None = None,
    require_physical_host: bool = False,
) -> dict[str, Any]:
    delivery_dir = delivery_dir.expanduser().resolve()
    app = app.expanduser().resolve()
    _require(delivery_dir.is_dir(), f"delivery directory missing: {delivery_dir}")
    _require(app.is_dir(), f"app bundle missing: {app}")

    delivery_path = delivery_dir / "FULL_MAC_DELIVERY.json"
    external_candidate_path = delivery_dir / "PHYSICAL_UAT_CANDIDATE.json"
    resources = app / "Contents" / "Resources"
    internal_candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    provenance_path = resources / "BUILD_PROVENANCE.json"
    readiness_path = resources / "RELEASE_READINESS.json"

    delivery = _json(delivery_path)
    external = _json(external_candidate_path)
    internal = _json(internal_candidate_path)
    provenance = _json(provenance_path)
    readiness = _json(readiness_path)

    _require(delivery.get("schema") == DELIVERY_SCHEMA, "unexpected delivery schema")
    _require(delivery.get("role") == EXPECTED_ROLE, "delivery is not a physical UAT candidate")
    _require(external.get("schema") == CANDIDATE_SCHEMA, "unexpected external candidate schema")
    _require(internal.get("schema") == CANDIDATE_SCHEMA, "unexpected embedded candidate schema")
    _require(provenance.get("schema") == PROVENANCE_SCHEMA, "unexpected build provenance schema")
    _require(readiness.get("schema") == READINESS_SCHEMA, "unexpected embedded readiness schema")

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

    _require(delivery.get("architecture") == EXPECTED_ARCH, "delivery is not arm64")
    _require(external.get("architecture") == EXPECTED_ARCH, "external candidate is not arm64")
    _require(internal.get("architecture") == EXPECTED_ARCH, "embedded candidate is not arm64")
    _require(provenance.get("architecture") == EXPECTED_ARCH, "build provenance is not arm64")
    _require(readiness.get("architecture") == EXPECTED_ARCH, "embedded readiness is not arm64")
    _require(delivery.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "delivery runtime wave drift")
    _require(external.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "external runtime wave drift")
    _require(internal.get("runtime_wave") == EXPECTED_RUNTIME_WAVE, "embedded runtime wave drift")
    _require(delivery.get("certification_guard_wave") == EXPECTED_GUARD_WAVE, "delivery certification guard drift")
    _require(external.get("certification_guard_wave") == EXPECTED_GUARD_WAVE, "external certification guard drift")
    _require(internal.get("certification_guard_wave") == EXPECTED_GUARD_WAVE, "embedded certification guard drift")

    source_sha = str(delivery.get("candidate_source_sha256") or "")
    _require(len(source_sha) == 64, "delivery candidate source SHA-256 malformed")
    _require(external.get("candidate_source_sha256") == source_sha, "external candidate source digest mismatch")
    _require(internal.get("candidate_source_sha256") == source_sha, "embedded candidate source digest mismatch")

    internal_manifest_sha = _sha256(internal_candidate_path)
    external_manifest_sha = _sha256(external_candidate_path)
    expected_manifest_sha = str(delivery.get("candidate_manifest_sha256") or "")
    _require(internal_manifest_sha == expected_manifest_sha, "embedded candidate manifest digest mismatch")
    _require(external_manifest_sha == expected_manifest_sha, "external candidate manifest digest mismatch")

    artifact_name = str(delivery.get("artifact") or "")
    _require(artifact_name.startswith("Binario-Marketing-IA-PHYSICAL-UAT-arm64-"), "unexpected artifact identity")
    artifact_path = delivery_dir / artifact_name
    _require(artifact_path.is_file(), f"candidate ZIP missing: {artifact_path}")
    artifact_sha = _sha256(artifact_path)
    _require(artifact_sha == delivery.get("artifact_sha256"), "candidate ZIP SHA-256 mismatch")
    checksum_path = delivery_dir / f"{artifact_name}.sha256"
    _require(checksum_path.is_file(), "candidate checksum file missing")
    checksum_line = checksum_path.read_text(encoding="utf-8").strip()
    _require(checksum_line == f"{artifact_sha}  {artifact_name}", "candidate checksum sidecar mismatch")

    for label, payload in (("delivery", delivery), ("external candidate", external), ("embedded candidate", internal)):
        if label == "delivery":
            _require(payload.get("release_ready") is False, f"{label} unexpectedly release-ready")
            _require(payload.get("release_tag") is None, f"{label} unexpectedly has release tag")
            _require(payload.get("production_ready") is False, f"{label} unexpectedly production-ready")
            _require(payload.get("physical_uat_required") is True, f"{label} physical UAT requirement missing")
            _require(payload.get("automatic_uat_pass") is False, f"{label} unexpectedly allows automatic UAT pass")
        else:
            boundary = payload.get("release_boundary") or {}
            physical = payload.get("physical_uat") or {}
            _require(boundary.get("release_ready") is False, f"{label} unexpectedly release-ready")
            _require(boundary.get("release_tag") is None, f"{label} unexpectedly has release tag")
            _require(boundary.get("production_ready") is False, f"{label} unexpectedly production-ready")
            _require(physical.get("required") is True, f"{label} physical UAT requirement missing")
            _require(physical.get("automatic_pass") is False, f"{label} unexpectedly allows automatic UAT pass")

    system = platform.system()
    machine = platform.machine().lower()
    is_ci = str(os.environ.get("GITHUB_ACTIONS") or "").lower() == "true" or str(os.environ.get("CI") or "").lower() == "true"
    physical_host = system == "Darwin" and machine == "arm64" and not is_ci
    if require_physical_host:
        _require(physical_host, f"physical UAT requires real non-CI Darwin arm64 host; got {system}/{machine}/CI={is_ci}")

    return {
        "schema": "binario.marketing.physical-uat-handoff-verification.v1",
        "git_sha": git_sha,
        "architecture": EXPECTED_ARCH,
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "candidate_source_sha256": source_sha,
        "candidate_manifest_sha256": expected_manifest_sha,
        "artifact": artifact_name,
        "artifact_sha256": artifact_sha,
        "host": {"system": system, "machine": machine, "is_ci": is_ci, "physical_gate_eligible": physical_host},
        "ready_for_operator_uat": physical_host if require_physical_host else True,
        "automatic_uat_pass": False,
        "release_authority": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify an extracted W83/W84 physical-UAT delivery before an operator starts UAT.")
    parser.add_argument("--delivery-dir", type=Path, required=True)
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--expected-git-sha")
    parser.add_argument("--require-physical-host", action="store_true")
    args = parser.parse_args()
    try:
        report = verify(
            args.delivery_dir,
            args.app,
            expected_git_sha=args.expected_git_sha,
            require_physical_host=args.require_physical_host,
        )
    except ValueError as exc:
        raise SystemExit(f"PHYSICAL UAT HANDOFF BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
