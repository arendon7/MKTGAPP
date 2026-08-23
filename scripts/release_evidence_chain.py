#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ASSET_SCHEMA = "binario.marketing.release-evidence-chain.v1"
AUTH_SCHEMA = "binario.marketing.release-authorization.v1"
RELEASE_SCHEMA = "binario.marketing.release.v2"
DISTRIBUTION_REBUILD_SCHEMA = "binario.marketing.distribution-rebuild.v1"
DISTRIBUTION_REBUILD_PURPOSE = "SOURCE_EQUIVALENT_DISTRIBUTION_REBUILD"
COMBINED_UAT_SCHEMA = "binario.marketing.combined-physical-uat-attestation.v1"
PRODUCTION_GATE_SCHEMA = "binario.marketing.release-readiness.v1"
RUNTIME_WAVE = 76
CERTIFICATION_GUARD_WAVE = 91
EXPECTED_ARCHITECTURES = {"arm64", "x86_64"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON evidence: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return data


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_file(path: Path) -> str:
    _require(path.is_file(), f"evidence file missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _seal(payload: dict[str, Any], field: str) -> dict[str, Any]:
    core = dict(payload)
    core.pop(field, None)
    result = dict(core)
    result[field] = _digest(core)
    return result


def _verify_seal(payload: dict[str, Any], field: str) -> None:
    expected = str(payload.get(field) or "")
    _require(len(expected) == 64, f"{field} missing or malformed")
    core = dict(payload)
    core.pop(field, None)
    _require(_digest(core) == expected, f"{field} mismatch")


def _source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for root in (source / "src", source / "web", source / "apps"):
        _require(root.is_dir(), f"distribution source root missing: {root}")
        files.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(source).as_posix()):
        relative = path.relative_to(source).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _validate_production_gate(
    data: dict[str, Any],
    *,
    git_sha: str,
    architecture: str,
    product_version: str,
    uat_evidence_file_sha256: str | None = None,
    uat_attestation_sha256: str | None = None,
    distribution_evidence_file_sha256: str | None = None,
    distribution_trust_evidence_sha256: str | None = None,
    distribution_rebuild_manifest_sha256: str | None = None,
) -> None:
    _require(data.get("schema") == PRODUCTION_GATE_SCHEMA, "unexpected production gate schema")
    _require(data.get("git_sha") == git_sha, "production gate git SHA mismatch")
    _require(data.get("architecture") == architecture, "production gate architecture mismatch")
    _require(data.get("version") == product_version, "production gate version mismatch")
    _require(data.get("stage") == "PRODUCTION_READY", "production gate stage is not PRODUCTION_READY")
    _require(data.get("production_ready") is True, "production gate did not pass")
    _require(not data.get("blocker_codes"), "production gate contains blockers")
    _require(data.get("distribution_trust_verified") is True, "production gate lacks distribution trust")
    _require(data.get("distribution_rebuild_consistent") is True, "production gate lacks rebuild consistency")
    _require(
        data.get("uat_binding_mode") in {"source_equivalent_arm64_rebuild", "source_equivalent_cross_arch_distribution"},
        "production gate UAT binding mode is not source-equivalent",
    )
    _require(data.get("source_equivalent_authorization") is True, "production gate lacks source-equivalent authorization")
    exact_bindings = {
        "uat_evidence_file_sha256": uat_evidence_file_sha256,
        "uat_attestation_sha256": uat_attestation_sha256,
        "distribution_evidence_file_sha256": distribution_evidence_file_sha256,
        "distribution_trust_evidence_sha256": distribution_trust_evidence_sha256,
        "distribution_rebuild_manifest_sha256": distribution_rebuild_manifest_sha256,
    }
    for key, expected in exact_bindings.items():
        if expected is not None:
            _require(data.get(key) == expected, f"production gate exact evidence binding mismatch: {key}")


def _validate_release_manifest(
    manifest: dict[str, Any],
    evidence: dict[str, Any],
    *,
    manifest_path: Path | None = None,
) -> None:
    _require(manifest.get("schema") == RELEASE_SCHEMA, "unexpected release manifest schema")
    for key in ("tag", "git_sha", "architecture", "product_version", "runtime_wave", "certification_guard_wave"):
        _require(manifest.get(key) == evidence.get(key), f"release manifest {key} mismatch")
    asset = evidence.get("asset") or {}
    _require(manifest.get("asset") == asset.get("name"), "release manifest asset mismatch")
    _require(manifest.get("sha256") == asset.get("sha256"), "release manifest asset SHA mismatch")
    _require(manifest.get("release_evidence") == evidence.get("evidence_file_name"), "release evidence filename mismatch")
    _require(manifest.get("release_evidence_sha256") == evidence.get("evidence_sha256"), "release evidence digest mismatch")
    _require(manifest.get("release_authority") is False, "per-architecture release manifest must not carry release authority")
    _require(manifest.get("publication_authority") is False, "per-architecture release manifest must not carry publication authority")
    if manifest_path is not None:
        _require(manifest_path.name == f"RELEASE-{evidence['architecture']}.json", "unexpected release manifest filename")


def build_asset_evidence(
    *,
    repo: Path,
    app: Path,
    uat_evidence: Path,
    distribution_evidence: Path,
    production_gate_evidence: Path,
    asset: Path,
    tag: str,
    architecture: str,
    evidence_file_name: str,
) -> dict[str, Any]:
    repo = repo.expanduser().resolve()
    app = app.expanduser().resolve()
    uat_evidence = uat_evidence.expanduser().resolve()
    distribution_evidence = distribution_evidence.expanduser().resolve()
    production_gate_evidence = production_gate_evidence.expanduser().resolve()
    asset = asset.expanduser().resolve()
    _require(architecture in EXPECTED_ARCHITECTURES, "unsupported release architecture")
    _require(app.is_dir(), f"release app missing: {app}")
    _require(asset.is_file(), f"release asset missing: {asset}")

    resources = app / "Contents/Resources"
    provenance_path = resources / "BUILD_PROVENANCE.json"
    readiness_path = resources / "RELEASE_READINESS.json"
    rebuild_path = resources / "DISTRIBUTION_REBUILD.json"
    source_root = resources / "source"
    provenance = _load_json(provenance_path)
    readiness = _load_json(readiness_path)
    rebuild = _load_json(rebuild_path)
    production_gate = _load_json(production_gate_evidence)

    git_sha = str(provenance.get("git_sha") or "")
    product_version = str(provenance.get("product_version") or "")
    _require(len(git_sha) == 40, "build provenance git SHA missing or malformed")
    _require(provenance.get("architecture") == architecture, "build provenance architecture mismatch")
    _require(bool(product_version), "build provenance product version missing")
    _require(tag == f"v{product_version}", "release tag/version mismatch")
    _require(readiness.get("git_sha") == git_sha, "embedded readiness git SHA mismatch")
    _require(readiness.get("architecture") == architecture, "embedded readiness architecture mismatch")
    _require(readiness.get("version") == product_version, "embedded readiness version mismatch")
    _require(readiness.get("release_ready_flag") is True, "embedded readiness release flag is false")
    _require(readiness.get("release_tag") == tag, "embedded readiness tag mismatch")

    source_sha256 = _source_digest(source_root)
    origin = rebuild.get("build_origin") if isinstance(rebuild.get("build_origin"), dict) else {}
    physical_uat = rebuild.get("physical_uat") if isinstance(rebuild.get("physical_uat"), dict) else {}
    _require(rebuild.get("schema") == DISTRIBUTION_REBUILD_SCHEMA, "unexpected distribution rebuild schema")
    _require(rebuild.get("purpose") == DISTRIBUTION_REBUILD_PURPOSE, "unexpected distribution rebuild purpose")
    _require(rebuild.get("git_sha") == git_sha, "distribution rebuild git SHA mismatch")
    _require(rebuild.get("architecture") == architecture, "distribution rebuild architecture mismatch")
    _require(rebuild.get("product_version") == product_version, "distribution rebuild version mismatch")
    _require(rebuild.get("runtime_wave") == RUNTIME_WAVE, "distribution rebuild runtime wave drift")
    _require(rebuild.get("source_sha256") == source_sha256, "distribution rebuild source digest mismatch")
    _require(origin.get("event") == "push" and origin.get("ref") == f"refs/tags/{tag}", "distribution rebuild tag origin mismatch")
    _require(origin.get("eligible_distribution_origin") is True, "distribution rebuild origin is not eligible")
    _require(physical_uat.get("claimed") is False and physical_uat.get("exact_bundle_tested") is False, "distribution rebuild improperly claims physical UAT")
    _require(physical_uat.get("authorization_mode") == "source_equivalent_only", "distribution rebuild authorization mode mismatch")
    _require(rebuild.get("release_authority") is False, "distribution rebuild must not carry release authority")

    sys.path.insert(0, str(repo / "scripts"))
    try:
        from verify_combined_uat_attestation import verify as verify_uat
        from verify_distribution_trust import verify as verify_distribution_trust
        uat = verify_uat(uat_evidence, expected_git_sha=git_sha)
        distribution = verify_distribution_trust(
            distribution_evidence,
            git_sha=git_sha,
            architecture=architecture,
            product_version=product_version,
        )
    finally:
        try:
            sys.path.remove(str(repo / "scripts"))
        except ValueError:
            pass

    _require(uat.get("schema") == COMBINED_UAT_SCHEMA, "unexpected UAT attestation schema")
    _require(uat.get("candidate_source_sha256") == source_sha256, "UAT/source equivalence mismatch")
    _require(uat.get("both_phases_passed") is True, "physical UAT attestation is not fully passed")
    _require(uat.get("release_authority") is False and uat.get("production_ready") is False, "UAT attestation improperly carries release authority")
    _require(distribution.get("release_authority") is False, "distribution trust improperly carries release authority")

    uat_file_sha256 = _sha256_file(uat_evidence)
    distribution_file_sha256 = _sha256_file(distribution_evidence)
    rebuild_manifest_sha256 = _sha256_file(rebuild_path)
    _validate_production_gate(
        production_gate,
        git_sha=git_sha,
        architecture=architecture,
        product_version=product_version,
        uat_evidence_file_sha256=uat_file_sha256,
        uat_attestation_sha256=str(uat.get("attestation_sha256") or ""),
        distribution_evidence_file_sha256=distribution_file_sha256,
        distribution_trust_evidence_sha256=str(distribution.get("evidence_sha256") or ""),
        distribution_rebuild_manifest_sha256=rebuild_manifest_sha256,
    )
    _require(production_gate.get("current_source_sha256") == source_sha256, "production gate source digest mismatch")
    _require(production_gate.get("distribution_architecture") == architecture, "production gate distribution architecture mismatch")
    _require(production_gate.get("uat_schema") == COMBINED_UAT_SCHEMA, "production gate UAT schema mismatch")

    gates = {
        "canonical_release_contract": True,
        "exact_git_sha_binding": True,
        "tag_version_binding": True,
        "physical_uat_attestation_verified": True,
        "source_equivalence_verified": True,
        "distribution_rebuild_verified": True,
        "developer_id_signature_verified": True,
        "apple_notarization_verified": True,
        "gatekeeper_verified": True,
        "production_gate_passed": True,
        "exact_evidence_digest_binding_verified": True,
        "immutable_asset_hashed": True,
    }
    payload = {
        "schema": ASSET_SCHEMA,
        "tag": tag,
        "git_sha": git_sha,
        "architecture": architecture,
        "product_version": product_version,
        "runtime_wave": RUNTIME_WAVE,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "source_sha256": source_sha256,
        "evidence_file_name": evidence_file_name,
        "asset": {
            "name": asset.name,
            "sha256": _sha256_file(asset),
            "size_bytes": asset.stat().st_size,
        },
        "physical_uat": {
            "schema": uat.get("schema"),
            "attestation_sha256": uat.get("attestation_sha256"),
            "evidence_file_sha256": uat_file_sha256,
            "candidate_source_sha256": uat.get("candidate_source_sha256"),
            "candidate_manifest_sha256": uat.get("candidate_manifest_sha256"),
            "physical_architecture": uat.get("architecture"),
        },
        "distribution_rebuild": {
            "schema": rebuild.get("schema"),
            "purpose": rebuild.get("purpose"),
            "manifest_sha256": rebuild_manifest_sha256,
            "source_sha256": rebuild.get("source_sha256"),
            "build_origin": origin,
        },
        "distribution_trust": {
            "schema": distribution.get("schema"),
            "evidence_sha256": distribution.get("evidence_sha256"),
            "evidence_file_sha256": distribution_file_sha256,
            "notary_submission_id": distribution.get("notary_submission_id"),
        },
        "production_gate": {
            "schema": production_gate.get("schema"),
            "evidence_file_sha256": _sha256_file(production_gate_evidence),
            "stage": production_gate.get("stage"),
            "uat_binding_mode": production_gate.get("uat_binding_mode"),
            "uat_evidence_file_sha256": production_gate.get("uat_evidence_file_sha256"),
            "uat_attestation_sha256": production_gate.get("uat_attestation_sha256"),
            "distribution_evidence_file_sha256": production_gate.get("distribution_evidence_file_sha256"),
            "distribution_trust_evidence_sha256": production_gate.get("distribution_trust_evidence_sha256"),
            "distribution_rebuild_manifest_sha256": production_gate.get("distribution_rebuild_manifest_sha256"),
        },
        "build_inputs": {
            "build_provenance_sha256": _sha256_file(provenance_path),
            "embedded_readiness_sha256": _sha256_file(readiness_path),
        },
        "authorization_gates": gates,
        "asset_authorized": True,
        "operational_authorization": False,
        "release_authority": False,
        "publication_authority": False,
        "production_ready": False,
        "mutations_performed": False,
    }
    return _seal(payload, "evidence_sha256")


def verify_asset_evidence(
    path: Path,
    *,
    asset_dir: Path,
    release_manifest: Path | None = None,
    expected_tag: str | None = None,
    expected_git_sha: str | None = None,
) -> dict[str, Any]:
    path = path.expanduser().resolve()
    asset_dir = asset_dir.expanduser().resolve()
    data = _load_json(path)
    _require(data.get("schema") == ASSET_SCHEMA, "unexpected release evidence schema")
    _verify_seal(data, "evidence_sha256")
    _require(data.get("evidence_file_name") == path.name, "release evidence filename binding mismatch")
    _require(data.get("architecture") in EXPECTED_ARCHITECTURES, "unsupported evidence architecture")
    _require(data.get("runtime_wave") == RUNTIME_WAVE, "release evidence runtime wave drift")
    _require(data.get("certification_guard_wave") == CERTIFICATION_GUARD_WAVE, "release evidence certification guard drift")
    if expected_tag is not None:
        _require(data.get("tag") == expected_tag, "release evidence tag mismatch")
    if expected_git_sha is not None:
        _require(data.get("git_sha") == expected_git_sha, "release evidence git SHA mismatch")
    _require(data.get("tag") == f"v{data.get('product_version')}", "release evidence tag/version mismatch")
    physical_uat = data.get("physical_uat") or {}
    rebuild = data.get("distribution_rebuild") or {}
    distribution = data.get("distribution_trust") or {}
    production_gate = data.get("production_gate") or {}
    _require(data.get("source_sha256") == physical_uat.get("candidate_source_sha256"), "release evidence UAT/source mismatch")
    _require(data.get("source_sha256") == rebuild.get("source_sha256"), "release evidence rebuild/source mismatch")
    _require(production_gate.get("uat_evidence_file_sha256") == physical_uat.get("evidence_file_sha256"), "production gate/UAT file digest mismatch")
    _require(production_gate.get("uat_attestation_sha256") == physical_uat.get("attestation_sha256"), "production gate/UAT attestation digest mismatch")
    _require(production_gate.get("distribution_evidence_file_sha256") == distribution.get("evidence_file_sha256"), "production gate/distribution evidence digest mismatch")
    _require(production_gate.get("distribution_trust_evidence_sha256") == distribution.get("evidence_sha256"), "production gate/distribution trust digest mismatch")
    _require(production_gate.get("distribution_rebuild_manifest_sha256") == rebuild.get("manifest_sha256"), "production gate/rebuild manifest digest mismatch")
    gates = data.get("authorization_gates") or {}
    _require(isinstance(gates, dict) and bool(gates) and all(value is True for value in gates.values()), "release evidence authorization gates are incomplete")
    _require(gates.get("exact_evidence_digest_binding_verified") is True, "exact evidence digest gate is missing")
    _require(data.get("asset_authorized") is True, "release asset is not authorized")
    _require(data.get("operational_authorization") is False, "per-architecture evidence must not carry operational authorization")
    _require(data.get("release_authority") is False, "per-architecture evidence must not carry release authority")
    _require(data.get("publication_authority") is False, "per-architecture evidence must not carry publication authority")
    _require(data.get("production_ready") is False, "per-architecture evidence must not claim production readiness")
    _require(data.get("mutations_performed") is False, "evidence generation must not claim publication mutations")

    asset = data.get("asset") or {}
    asset_path = asset_dir / str(asset.get("name") or "")
    _require(asset_path.is_file(), f"release asset missing for evidence: {asset_path}")
    _require(_sha256_file(asset_path) == asset.get("sha256"), "release asset digest mismatch")
    _require(asset_path.stat().st_size == asset.get("size_bytes"), "release asset size mismatch")

    if release_manifest is not None:
        manifest_path = release_manifest.expanduser().resolve()
        _validate_release_manifest(_load_json(manifest_path), data, manifest_path=manifest_path)
    return data


def build_release_manifest(evidence: dict[str, Any]) -> dict[str, Any]:
    asset = evidence["asset"]
    return {
        "schema": RELEASE_SCHEMA,
        "tag": evidence["tag"],
        "git_sha": evidence["git_sha"],
        "architecture": evidence["architecture"],
        "product_version": evidence["product_version"],
        "asset": asset["name"],
        "sha256": asset["sha256"],
        "runtime_wave": RUNTIME_WAVE,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "release_evidence": evidence["evidence_file_name"],
        "release_evidence_sha256": evidence["evidence_sha256"],
        "release_authority": False,
        "publication_authority": False,
    }


def build_release_authorization(arm64: dict[str, Any], x86_64: dict[str, Any]) -> dict[str, Any]:
    _require(arm64.get("architecture") == "arm64", "arm64 evidence architecture mismatch")
    _require(x86_64.get("architecture") == "x86_64", "x86_64 evidence architecture mismatch")
    shared_fields = ("tag", "git_sha", "product_version", "runtime_wave", "source_sha256")
    for key in shared_fields:
        _require(arm64.get(key) == x86_64.get(key), f"cross-architecture {key} mismatch")
    arm_uat = arm64.get("physical_uat") or {}
    x86_uat = x86_64.get("physical_uat") or {}
    for key in ("attestation_sha256", "evidence_file_sha256", "candidate_source_sha256", "candidate_manifest_sha256"):
        _require(arm_uat.get(key) == x86_uat.get(key), f"cross-architecture UAT {key} mismatch")
    _require(arm64.get("asset", {}).get("name") != x86_64.get("asset", {}).get("name"), "native release assets must be distinct")
    _require(arm64.get("asset_authorized") is True and x86_64.get("asset_authorized") is True, "both native assets must be authorized")

    payload = {
        "schema": AUTH_SCHEMA,
        "tag": arm64["tag"],
        "git_sha": arm64["git_sha"],
        "product_version": arm64["product_version"],
        "runtime_wave": RUNTIME_WAVE,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "source_sha256": arm64["source_sha256"],
        "physical_uat": {
            "attestation_sha256": arm_uat.get("attestation_sha256"),
            "evidence_file_sha256": arm_uat.get("evidence_file_sha256"),
            "candidate_source_sha256": arm_uat.get("candidate_source_sha256"),
            "candidate_manifest_sha256": arm_uat.get("candidate_manifest_sha256"),
            "physical_architecture": "arm64",
        },
        "native_assets": {
            "arm64": {
                "asset": arm64["asset"]["name"],
                "sha256": arm64["asset"]["sha256"],
                "release_evidence": arm64["evidence_file_name"],
                "release_evidence_sha256": arm64["evidence_sha256"],
            },
            "x86_64": {
                "asset": x86_64["asset"]["name"],
                "sha256": x86_64["asset"]["sha256"],
                "release_evidence": x86_64["evidence_file_name"],
                "release_evidence_sha256": x86_64["evidence_sha256"],
            },
        },
        "cross_architecture_gates": {
            "same_git_sha": True,
            "same_tag_and_version": True,
            "same_source_digest": True,
            "same_physical_uat_attestation": True,
            "arm64_asset_authorized": True,
            "x86_64_asset_authorized": True,
            "distinct_native_assets": True,
            "each_native_chain_has_exact_evidence_binding": True,
        },
        "operational_authorization": True,
        "release_authority": True,
        "publication_authority": True,
        "production_ready": True,
        "publication_performed": False,
        "mutations_performed": False,
    }
    return _seal(payload, "authorization_sha256")


def verify_release_authorization(
    authorization_path: Path,
    *,
    arm64_evidence: Path,
    x86_evidence: Path,
    asset_dir: Path,
    arm64_release_manifest: Path,
    x86_release_manifest: Path,
    expected_tag: str | None = None,
    expected_git_sha: str | None = None,
) -> dict[str, Any]:
    arm64 = verify_asset_evidence(
        arm64_evidence,
        asset_dir=asset_dir,
        release_manifest=arm64_release_manifest,
        expected_tag=expected_tag,
        expected_git_sha=expected_git_sha,
    )
    x86_64 = verify_asset_evidence(
        x86_evidence,
        asset_dir=asset_dir,
        release_manifest=x86_release_manifest,
        expected_tag=expected_tag,
        expected_git_sha=expected_git_sha,
    )
    expected = build_release_authorization(arm64, x86_64)
    actual = _load_json(authorization_path.expanduser().resolve())
    _require(actual == expected, "release authorization manifest drift")
    _verify_seal(actual, "authorization_sha256")
    _require(actual.get("operational_authorization") is True, "operational authorization missing")
    _require(actual.get("release_authority") is True, "release authority missing")
    _require(actual.get("publication_authority") is True, "publication authority missing")
    _require(actual.get("production_ready") is True, "release authorization is not production ready")
    _require(actual.get("publication_performed") is False, "authorization must precede publication")
    _require(actual.get("mutations_performed") is False, "authorization generation must not perform publication")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and verify the fail-closed W91 release evidence chain.")
    sub = parser.add_subparsers(dest="command", required=True)

    write_asset = sub.add_parser("write-asset")
    write_asset.add_argument("--repo", type=Path, default=Path.cwd())
    write_asset.add_argument("--app", type=Path, required=True)
    write_asset.add_argument("--uat-evidence", type=Path, required=True)
    write_asset.add_argument("--distribution-evidence", type=Path, required=True)
    write_asset.add_argument("--production-gate-evidence", type=Path, required=True)
    write_asset.add_argument("--asset", type=Path, required=True)
    write_asset.add_argument("--tag", required=True)
    write_asset.add_argument("--architecture", choices=sorted(EXPECTED_ARCHITECTURES), required=True)
    write_asset.add_argument("--output", type=Path, required=True)
    write_asset.add_argument("--release-manifest", type=Path, required=True)

    verify_asset = sub.add_parser("verify-asset")
    verify_asset.add_argument("--evidence", type=Path, required=True)
    verify_asset.add_argument("--asset-dir", type=Path, required=True)
    verify_asset.add_argument("--release-manifest", type=Path, required=True)
    verify_asset.add_argument("--expected-tag")
    verify_asset.add_argument("--expected-git-sha")

    authorize = sub.add_parser("authorize")
    authorize.add_argument("--arm64-evidence", type=Path, required=True)
    authorize.add_argument("--x86-evidence", type=Path, required=True)
    authorize.add_argument("--asset-dir", type=Path, required=True)
    authorize.add_argument("--arm64-release-manifest", type=Path, required=True)
    authorize.add_argument("--x86-release-manifest", type=Path, required=True)
    authorize.add_argument("--expected-tag")
    authorize.add_argument("--expected-git-sha")
    authorize.add_argument("--output", type=Path, required=True)

    verify_auth = sub.add_parser("verify-authorization")
    verify_auth.add_argument("--authorization", type=Path, required=True)
    verify_auth.add_argument("--arm64-evidence", type=Path, required=True)
    verify_auth.add_argument("--x86-evidence", type=Path, required=True)
    verify_auth.add_argument("--asset-dir", type=Path, required=True)
    verify_auth.add_argument("--arm64-release-manifest", type=Path, required=True)
    verify_auth.add_argument("--x86-release-manifest", type=Path, required=True)
    verify_auth.add_argument("--expected-tag")
    verify_auth.add_argument("--expected-git-sha")

    args = parser.parse_args()
    try:
        if args.command == "write-asset":
            output = args.output.expanduser().resolve()
            evidence = build_asset_evidence(
                repo=args.repo,
                app=args.app,
                uat_evidence=args.uat_evidence,
                distribution_evidence=args.distribution_evidence,
                production_gate_evidence=args.production_gate_evidence,
                asset=args.asset,
                tag=args.tag,
                architecture=args.architecture,
                evidence_file_name=output.name,
            )
            _write_json(output, evidence)
            manifest = build_release_manifest(evidence)
            _write_json(args.release_manifest.expanduser().resolve(), manifest)
            print(json.dumps({
                "schema": evidence["schema"],
                "architecture": evidence["architecture"],
                "asset": evidence["asset"]["name"],
                "asset_sha256": evidence["asset"]["sha256"],
                "evidence_sha256": evidence["evidence_sha256"],
                "asset_authorized": evidence["asset_authorized"],
                "release_authority": evidence["release_authority"],
                "publication_authority": evidence["publication_authority"],
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.command == "verify-asset":
            report = verify_asset_evidence(
                args.evidence,
                asset_dir=args.asset_dir,
                release_manifest=args.release_manifest,
                expected_tag=args.expected_tag,
                expected_git_sha=args.expected_git_sha,
            )
            print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        if args.command == "authorize":
            arm64 = verify_asset_evidence(
                args.arm64_evidence,
                asset_dir=args.asset_dir,
                release_manifest=args.arm64_release_manifest,
                expected_tag=args.expected_tag,
                expected_git_sha=args.expected_git_sha,
            )
            x86_64 = verify_asset_evidence(
                args.x86_evidence,
                asset_dir=args.asset_dir,
                release_manifest=args.x86_release_manifest,
                expected_tag=args.expected_tag,
                expected_git_sha=args.expected_git_sha,
            )
            authorization = build_release_authorization(arm64, x86_64)
            _write_json(args.output.expanduser().resolve(), authorization)
            print(json.dumps(authorization, ensure_ascii=False, indent=2, sort_keys=True))
            return 0

        report = verify_release_authorization(
            args.authorization,
            arm64_evidence=args.arm64_evidence,
            x86_evidence=args.x86_evidence,
            asset_dir=args.asset_dir,
            arm64_release_manifest=args.arm64_release_manifest,
            x86_release_manifest=args.x86_release_manifest,
            expected_tag=args.expected_tag,
            expected_git_sha=args.expected_git_sha,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except ValueError as exc:
        raise SystemExit(f"W91 RELEASE EVIDENCE BLOCKED: {exc}") from exc


if __name__ == "__main__":
    raise SystemExit(main())
