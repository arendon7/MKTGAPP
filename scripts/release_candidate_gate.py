#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
RELEASE_UAT_SCHEMA = "binario.marketing.release-uat-evidence.v1"
PRODUCT_UAT_SCHEMA = "binario.marketing.product-uat-evidence.v2"


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


def _uat_passed(path: Path | None, *, git_sha: str | None, architecture: str | None, candidate_source_sha256: str | None = None, candidate_manifest_sha256: str | None = None) -> tuple[bool, dict[str, Any] | None]:
    if path is None:
        return False, None
    data = _load_json(path)
    if data.get("schema") != RELEASE_UAT_SCHEMA:
        return False, data
    if not git_sha or data.get("git_sha") != git_sha:
        return False, data
    if architecture and data.get("architecture") not in {architecture, "universal"}:
        return False, data
    if candidate_source_sha256 is not None and data.get("candidate_source_sha256") != candidate_source_sha256:
        return False, data
    if candidate_manifest_sha256 is not None and data.get("candidate_manifest_sha256") != candidate_manifest_sha256:
        return False, data
    if candidate_source_sha256 is not None and data.get("runtime_wave") != 76:
        return False, data
    return bool(data.get("uat_passed") is True and data.get("overall") == "UAT_PASS"), data


def _product_uat_passed(path: Path | None, *, git_sha: str | None, architecture: str | None, product_version: str | None, candidate_source_sha256: str | None, candidate_manifest_sha256: str | None) -> tuple[bool, dict[str, Any] | None]:
    if path is None:
        return False, None
    data = _load_json(path)
    checks = (
        data.get("schema") == PRODUCT_UAT_SCHEMA,
        bool(git_sha) and data.get("git_sha") == git_sha,
        data.get("architecture") == architecture == "arm64",
        data.get("product_version") == product_version,
        data.get("runtime_wave") == 76,
        data.get("candidate_source_sha256") == candidate_source_sha256,
        data.get("candidate_manifest_sha256") == candidate_manifest_sha256,
        isinstance(data.get("session_evidence_sha256"), str) and len(data.get("session_evidence_sha256")) == 64,
        data.get("product_uat_passed") is True,
        data.get("release_authority") is False,
        data.get("production_ready") is False,
    )
    return all(checks), data


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
    ap.add_argument("--uat-evidence", type=Path, help="Phase B release operational UAT evidence.")
    ap.add_argument("--product-uat-evidence", type=Path, help="Phase A physical product UAT evidence exported by collect_product_uat.py.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--production", action="store_true")
    mode.add_argument("--expect-blocked", action="store_true")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    sys.path.insert(0, str(repo / "src"))
    from binario_marketing.release_readiness import evaluate_release_readiness

    provenance = embedded = candidate = None
    candidate_source_sha256 = candidate_manifest_sha256 = None
    signing_mode = notarized = git_sha = architecture = product_version = None
    source_kwargs: dict[str, Any] = {}
    if args.app:
        app = args.app.expanduser().resolve()
        resources = app / "Contents" / "Resources"
        provenance = _load_json(resources / "BUILD_PROVENANCE.json")
        embedded = _load_json(resources / "RELEASE_READINESS.json")
        candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
        if candidate_path.is_file():
            candidate = _load_json(candidate_path)
            candidate_source_sha256 = candidate.get("candidate_source_sha256")
            candidate_manifest_sha256 = _sha256(candidate_path)
        signing_mode = provenance.get("signing_mode")
        notarized = provenance.get("notarized")
        git_sha = provenance.get("git_sha")
        architecture = provenance.get("architecture")
        product_version = provenance.get("product_version")
        source_kwargs = {"version": embedded.get("version"), "release_ready": bool(embedded.get("release_ready_flag")), "release_tag": embedded.get("release_tag")}

    release_uat_passed, release_uat = _uat_passed(
        args.uat_evidence,
        git_sha=git_sha,
        architecture=architecture,
        candidate_source_sha256=candidate_source_sha256,
        candidate_manifest_sha256=candidate_manifest_sha256,
    )
    product_uat_passed, product_uat = _product_uat_passed(
        args.product_uat_evidence,
        git_sha=git_sha,
        architecture=architecture,
        product_version=product_version,
        candidate_source_sha256=candidate_source_sha256,
        candidate_manifest_sha256=candidate_manifest_sha256,
    )
    dual_uat_passed = bool(release_uat_passed and product_uat_passed)

    report = evaluate_release_readiness(
        **source_kwargs,
        signing_mode=signing_mode,
        notarized=notarized,
        uat_passed=dual_uat_passed,
        git_sha=git_sha,
        architecture=architecture,
    )
    if embedded:
        report["embedded_source_state_matches"] = all(report.get(key) == embedded.get(key) for key in ("version", "release_ready_flag", "release_tag", "git_sha", "architecture", "signing_mode", "notarized"))
        if not report["embedded_source_state_matches"]:
            _append_blocker(report, "embedded_state_mismatch", "candidate", "El estado embebido del candidato no coincide con la evaluación reproducida.")

    candidate_consistent = None
    candidate_origin: dict[str, Any] = {}
    if provenance and architecture == "arm64":
        candidate_origin = candidate.get("build_origin") if candidate and isinstance(candidate.get("build_origin"), dict) else {}
        ref = str(candidate_origin.get("ref") or "")
        trusted_origin = bool(candidate_origin.get("event") == "push" and (ref == "refs/heads/main" or ref.startswith("refs/tags/v")) and candidate_origin.get("trusted_for_physical_uat") is True and candidate and candidate.get("physical_uat", {}).get("eligible_build_origin") is True)
        candidate_consistent = bool(candidate and candidate.get("schema") == CANDIDATE_SCHEMA and candidate.get("role") == "PHYSICAL_UAT_CANDIDATE_ONLY" and trusted_origin and candidate.get("git_sha") == git_sha and candidate.get("architecture") == architecture and candidate.get("product_version") == product_version and candidate.get("runtime_wave") == 76 and candidate.get("certification_guard_wave") == 84 and isinstance(candidate_source_sha256, str) and len(candidate_source_sha256) == 64)
        if not candidate_consistent:
            _append_blocker(report, "physical_uat_candidate_manifest_missing_or_invalid", "uat", "El bundle arm64 no contiene un manifiesto W84 válido de origen GitHub confiable.")
        if not product_uat_passed:
            _append_blocker(report, "physical_product_uat_missing_or_invalid", "uat", "Falta Phase A válida y ligada al candidato exacto.")
        if not release_uat_passed:
            _append_blocker(report, "release_operational_uat_missing_or_invalid", "uat", "Falta Phase B válida y ligada al candidato exacto.")
        if product_uat is not None and release_uat is not None:
            shared = ("git_sha", "candidate_source_sha256", "candidate_manifest_sha256")
            if any(product_uat.get(key) != release_uat.get(key) for key in shared):
                _append_blocker(report, "dual_physical_uat_binding_mismatch", "uat", "Phase A y Phase B no pertenecen al mismo candidato exacto.")

    report.update({
        "app_evaluated": str(args.app.expanduser().resolve()) if args.app else None,
        "uat_evidence": str(args.uat_evidence.expanduser().resolve()) if args.uat_evidence else None,
        "product_uat_evidence": str(args.product_uat_evidence.expanduser().resolve()) if args.product_uat_evidence else None,
        "provenance_schema": provenance.get("schema") if provenance else None,
        "embedded_readiness_schema": embedded.get("schema") if embedded else None,
        "candidate_schema": candidate.get("schema") if candidate else None,
        "candidate_role": candidate.get("role") if candidate else None,
        "candidate_build_origin": candidate_origin,
        "candidate_source_sha256": candidate_source_sha256,
        "candidate_manifest_sha256": candidate_manifest_sha256,
        "candidate_manifest_consistent": candidate_consistent,
        "product_uat_schema": product_uat.get("schema") if product_uat else None,
        "release_uat_schema": release_uat.get("schema") if release_uat else None,
        "physical_product_uat_passed": product_uat_passed,
        "release_operational_uat_passed": release_uat_passed,
        "dual_physical_uat_passed": dual_uat_passed,
    })
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if args.production:
        return 0 if report["production_ready"] else 2
    if args.expect_blocked:
        return 0 if not report["production_ready"] else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
