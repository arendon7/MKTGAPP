#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
RAW_UAT_SCHEMA = "binario.marketing.release-uat-evidence.v1"
COMBINED_UAT_SCHEMA = "binario.marketing.combined-physical-uat-attestation.v1"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 84


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"missing JSON evidence: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid JSON evidence: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"JSON evidence must be an object: {path}")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for root in (source / "src", source / "web", source / "apps"):
        if not root.is_dir():
            raise SystemExit(f"candidate source root missing: {root}")
        files.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(source).as_posix()):
        relative = path.relative_to(source).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _combined_uat_valid(data: dict[str, Any]) -> bool:
    if data.get("schema") != COMBINED_UAT_SCHEMA:
        return False
    binding = data.get("binding") or {}
    phase_a = data.get("phase_a") or {}
    phase_b = data.get("phase_b") or {}
    if not isinstance(binding, dict) or not isinstance(phase_a, dict) or not isinstance(phase_b, dict):
        return False
    try:
        required_scenarios = int(phase_a.get("required_scenarios") or 0)
        passed_scenarios = int(phase_a.get("passed_scenarios") or 0)
        required_gates = int(phase_b.get("required_gates") or 0)
        passed_gates = int(phase_b.get("passed_gates") or 0)
    except (TypeError, ValueError):
        return False
    if required_scenarios <= 0 or passed_scenarios != required_scenarios:
        return False
    if required_gates != 12 or passed_gates != required_gates or phase_b.get("overall") != "UAT_PASS":
        return False
    if data.get("both_phases_passed") is not True or data.get("release_authority") is not False or data.get("production_ready") is not False:
        return False
    expected_sha = str(data.get("attestation_sha256") or "")
    if len(expected_sha) != 64:
        return False
    core = dict(data)
    core.pop("generated_at", None)
    core.pop("attestation_sha256", None)
    return _digest(core) == expected_sha


def _uat_passed(
    path: Path | None,
    *,
    git_sha: str | None,
    architecture: str | None,
    product_version: str | None,
    current_source_sha256: str | None,
    candidate_source_sha256: str | None = None,
    candidate_manifest_sha256: str | None = None,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    if path is None:
        return False, None, None
    data = _load_json(path)
    schema = data.get("schema")
    if schema == RAW_UAT_SCHEMA:
        if not git_sha or data.get("git_sha") != git_sha:
            return False, data, None
        if architecture and data.get("architecture") not in {architecture, "universal"}:
            return False, data, None
        if candidate_source_sha256 is not None and data.get("candidate_source_sha256") != candidate_source_sha256:
            return False, data, None
        if candidate_manifest_sha256 is not None and data.get("candidate_manifest_sha256") != candidate_manifest_sha256:
            return False, data, None
        if candidate_source_sha256 is not None and data.get("runtime_wave") != EXPECTED_RUNTIME_WAVE:
            return False, data, None
        passed = bool(data.get("uat_passed") is True and data.get("overall") == "UAT_PASS")
        return passed, data, "exact_raw_release_uat" if passed else None
    if schema == COMBINED_UAT_SCHEMA:
        if not _combined_uat_valid(data):
            return False, data, None
        binding = data.get("binding") or {}
        if not git_sha or binding.get("git_sha") != git_sha:
            return False, data, None
        if product_version and binding.get("product_version") != product_version:
            return False, data, None
        if binding.get("architecture") != "arm64":
            return False, data, None
        if binding.get("runtime_wave") != EXPECTED_RUNTIME_WAVE or binding.get("certification_guard_wave") != EXPECTED_GUARD_WAVE:
            return False, data, None
        source_sha = str(binding.get("candidate_source_sha256") or "")
        if current_source_sha256 is None or source_sha != current_source_sha256:
            return False, data, None
        attested_manifest = str(binding.get("candidate_manifest_sha256") or "")
        if architecture == "arm64" and candidate_manifest_sha256 and attested_manifest == candidate_manifest_sha256:
            return True, data, "exact_physical_candidate"
        if architecture == "arm64":
            return True, data, "source_equivalent_arm64_rebuild"
        if architecture == "x86_64":
            return True, data, "source_equivalent_cross_arch_distribution"
    return False, data, None


def _append_blocker(report: dict[str, Any], code: str, scope: str, message: str) -> None:
    if code not in report["blocker_codes"]:
        report["blocker_codes"].append(code)
        report["blockers"].append({"code": code, "scope": scope, "message": message})
    report["production_ready"] = False
    report["stage"] = "RELEASE_CANDIDATE_BLOCKED"


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate BINARIO Marketing release readiness without bypassing production gates.")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--app", type=Path)
    ap.add_argument("--uat-evidence", type=Path)
    ap.add_argument("--distribution-evidence", type=Path)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--production", action="store_true")
    mode.add_argument("--expect-blocked", action="store_true")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    sys.path.insert(0, str(repo / "src"))
    sys.path.insert(0, str(repo / "scripts"))
    from binario_marketing.release_readiness import evaluate_release_readiness
    from verify_distribution_trust import verify as verify_distribution_trust

    provenance = embedded = candidate = None
    candidate_source_sha256 = candidate_manifest_sha256 = current_source_sha256 = None
    signing_mode = notarized = git_sha = architecture = product_version = None
    source_kwargs: dict[str, Any] = {}
    distribution: dict[str, Any] | None = None

    if args.app:
        app = args.app.expanduser().resolve()
        resources = app / "Contents/Resources"
        provenance = _load_json(resources / "BUILD_PROVENANCE.json")
        embedded = _load_json(resources / "RELEASE_READINESS.json")
        candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
        if candidate_path.is_file():
            candidate = _load_json(candidate_path)
            candidate_source_sha256 = candidate.get("candidate_source_sha256")
            candidate_manifest_sha256 = _sha256(candidate_path)
        source_root = resources / "source"
        if source_root.is_dir():
            current_source_sha256 = _source_digest(source_root)
        signing_mode = provenance.get("signing_mode")
        notarized = provenance.get("notarized")
        git_sha = provenance.get("git_sha")
        architecture = provenance.get("architecture")
        product_version = provenance.get("product_version")
        source_kwargs = {
            "version": embedded.get("version"),
            "release_ready": bool(embedded.get("release_ready_flag")),
            "release_tag": embedded.get("release_tag"),
        }

    if args.distribution_evidence:
        try:
            distribution = verify_distribution_trust(
                args.distribution_evidence,
                git_sha=git_sha,
                architecture=architecture,
                product_version=product_version,
            )
        except ValueError as exc:
            raise SystemExit(f"DISTRIBUTION TRUST BLOCKED: {exc}") from exc
        signing_mode = "developer_id"
        notarized = True

    uat_passed = False
    uat: dict[str, Any] | None = None
    uat_binding_mode: str | None = None
    if args.app or args.uat_evidence:
        uat_passed, uat, uat_binding_mode = _uat_passed(
            args.uat_evidence,
            git_sha=git_sha,
            architecture=architecture,
            product_version=product_version,
            current_source_sha256=current_source_sha256,
            candidate_source_sha256=candidate_source_sha256,
            candidate_manifest_sha256=candidate_manifest_sha256,
        )

    report = evaluate_release_readiness(
        **source_kwargs,
        signing_mode=signing_mode,
        notarized=notarized,
        uat_passed=uat_passed,
        git_sha=git_sha,
        architecture=architecture,
    )

    if embedded:
        source_keys = ("version", "release_ready_flag", "release_tag", "git_sha", "architecture")
        report["embedded_source_state_matches"] = all(report.get(key) == embedded.get(key) for key in source_keys)
        if not report["embedded_source_state_matches"]:
            _append_blocker(report, "embedded_state_mismatch", "candidate", "El estado embebido del candidato no coincide con la evaluación reproducida.")
        report["embedded_signing_mode"] = embedded.get("signing_mode")
        report["embedded_notarized"] = embedded.get("notarized")
        report["distribution_trust_supersedes_embedded_notarization"] = distribution is not None

    candidate_consistent = None
    candidate_origin: dict[str, Any] = {}
    if provenance and architecture == "arm64":
        candidate_origin = candidate.get("build_origin") if candidate and isinstance(candidate.get("build_origin"), dict) else {}
        ref = str(candidate_origin.get("ref") or "")
        trusted_origin = bool(
            candidate_origin.get("event") == "push"
            and (ref == "refs/heads/main" or ref.startswith("refs/tags/v"))
            and candidate_origin.get("trusted_for_physical_uat") is True
            and candidate
            and candidate.get("physical_uat", {}).get("eligible_build_origin") is True
        )
        candidate_consistent = bool(
            candidate
            and candidate.get("schema") == CANDIDATE_SCHEMA
            and candidate.get("role") == "PHYSICAL_UAT_CANDIDATE_ONLY"
            and trusted_origin
            and candidate.get("git_sha") == git_sha
            and candidate.get("architecture") == architecture
            and candidate.get("product_version") == product_version
            and candidate.get("runtime_wave") == EXPECTED_RUNTIME_WAVE
            and candidate.get("certification_guard_wave") == EXPECTED_GUARD_WAVE
            and isinstance(candidate_source_sha256, str)
            and len(candidate_source_sha256) == 64
            and candidate_source_sha256 == current_source_sha256
        )
        if not candidate_consistent:
            _append_blocker(report, "physical_uat_candidate_manifest_missing_or_invalid", "uat", "El bundle arm64 no contiene un manifiesto W84 válido de origen GitHub confiable.")

    if uat is not None and not uat_passed:
        if uat.get("schema") == RAW_UAT_SCHEMA and architecture == "arm64":
            if uat.get("git_sha") == git_sha and uat.get("candidate_source_sha256") != candidate_source_sha256:
                _append_blocker(report, "physical_uat_candidate_source_mismatch", "uat", "La evidencia UAT pertenece a una fuente distinta del candidato físico actual.")
            if uat.get("git_sha") == git_sha and uat.get("candidate_manifest_sha256") != candidate_manifest_sha256:
                _append_blocker(report, "physical_uat_candidate_manifest_mismatch", "uat", "La evidencia UAT no coincide con el manifiesto exacto del candidato físico actual.")
        elif uat.get("schema") == COMBINED_UAT_SCHEMA:
            binding = uat.get("binding") or {}
            if binding.get("git_sha") == git_sha and binding.get("candidate_source_sha256") != current_source_sha256:
                _append_blocker(report, "physical_uat_source_equivalence_mismatch", "uat", "La atestación física no corresponde al digest de fuente del build de distribución actual.")

    if args.production and distribution is None:
        _append_blocker(report, "distribution_trust_evidence_missing", "distribution", "El gate de producción exige evidencia verificada de Developer ID + notarización + Gatekeeper.")

    attestation_binding = uat.get("binding") if uat and uat.get("schema") == COMBINED_UAT_SCHEMA else {}
    report.update({
        "app_evaluated": str(args.app.expanduser().resolve()) if args.app else None,
        "uat_evidence": str(args.uat_evidence.expanduser().resolve()) if args.uat_evidence else None,
        "distribution_evidence": str(args.distribution_evidence.expanduser().resolve()) if args.distribution_evidence else None,
        "distribution_trust_schema": distribution.get("schema") if distribution else None,
        "distribution_trust_verified": distribution is not None,
        "distribution_notary_submission_id": distribution.get("notary_submission_id") if distribution else None,
        "provenance_schema": provenance.get("schema") if provenance else None,
        "embedded_readiness_schema": embedded.get("schema") if embedded else None,
        "candidate_schema": candidate.get("schema") if candidate else None,
        "candidate_role": candidate.get("role") if candidate else None,
        "candidate_build_origin": candidate_origin,
        "candidate_source_sha256": candidate_source_sha256,
        "current_source_sha256": current_source_sha256,
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "candidate_manifest_consistent": candidate_consistent,
        "uat_schema": uat.get("schema") if uat else None,
        "uat_binding_mode": uat_binding_mode,
        "uat_physical_architecture": attestation_binding.get("architecture") if attestation_binding else (uat.get("architecture") if uat else None),
        "distribution_architecture": architecture,
        "physical_uat_exact_bundle_binding": uat_binding_mode in {"exact_physical_candidate", "exact_raw_release_uat"},
        "source_equivalent_authorization": uat_binding_mode in {"source_equivalent_arm64_rebuild", "source_equivalent_cross_arch_distribution"},
        "x86_physical_uat_claimed": False,
    })
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.production:
        return 0 if report["production_ready"] else 2
    if args.expect_blocked:
        return 0 if not report["production_ready"] else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
