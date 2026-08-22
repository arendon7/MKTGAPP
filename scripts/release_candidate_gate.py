#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"


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


def _uat_passed(
    path: Path | None,
    *,
    git_sha: str | None,
    architecture: str | None,
    candidate_source_sha256: str | None = None,
    candidate_manifest_sha256: str | None = None,
) -> tuple[bool, dict[str, Any] | None]:
    if path is None:
        return False, None
    data = _load_json(path)
    if data.get("schema") != "binario.marketing.release-uat-evidence.v1":
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


def _append_blocker(report: dict[str, Any], code: str, scope: str, message: str) -> None:
    if code not in report["blocker_codes"]:
        report["blocker_codes"].append(code)
        report["blockers"].append({"code": code, "scope": scope, "message": message})
    report["production_ready"] = False
    report["stage"] = "RELEASE_CANDIDATE_BLOCKED"


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate BINARIO Marketing release readiness without bypassing production gates.")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--app", type=Path, help="Optional built .app candidate to evaluate.")
    ap.add_argument("--uat-evidence", type=Path, help="Optional physical UAT evidence bound to the candidate SHA/digests.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--production", action="store_true", help="Exit non-zero unless the candidate is production ready.")
    mode.add_argument("--expect-blocked", action="store_true", help="Exit non-zero if the candidate is unexpectedly production ready.")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    sys.path.insert(0, str(repo / "src"))
    from binario_marketing.release_readiness import evaluate_release_readiness

    provenance: dict[str, Any] | None = None
    embedded: dict[str, Any] | None = None
    candidate: dict[str, Any] | None = None
    candidate_manifest_path: Path | None = None
    candidate_source_sha256: str | None = None
    candidate_manifest_sha256: str | None = None
    signing_mode = notarized = git_sha = architecture = None
    source_kwargs: dict[str, Any] = {}
    if args.app:
        app = args.app.expanduser().resolve()
        resources = app / "Contents" / "Resources"
        provenance = _load_json(resources / "BUILD_PROVENANCE.json")
        embedded = _load_json(resources / "RELEASE_READINESS.json")
        candidate_manifest_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
        if candidate_manifest_path.is_file():
            candidate = _load_json(candidate_manifest_path)
            candidate_source_sha256 = candidate.get("candidate_source_sha256")
            candidate_manifest_sha256 = _sha256(candidate_manifest_path)
        signing_mode = provenance.get("signing_mode")
        notarized = provenance.get("notarized")
        git_sha = provenance.get("git_sha")
        architecture = provenance.get("architecture")
        source_kwargs = {
            "version": embedded.get("version"),
            "release_ready": bool(embedded.get("release_ready_flag")),
            "release_tag": embedded.get("release_tag"),
        }

    uat_passed: bool | None = None
    uat: dict[str, Any] | None = None
    if args.app or args.uat_evidence:
        uat_passed, uat = _uat_passed(
            args.uat_evidence,
            git_sha=git_sha,
            architecture=architecture,
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
        report["embedded_source_state_matches"] = all(
            report.get(key) == embedded.get(key)
            for key in ("version", "release_ready_flag", "release_tag", "git_sha", "architecture", "signing_mode", "notarized")
        )
        if not report["embedded_source_state_matches"]:
            _append_blocker(
                report,
                "embedded_state_mismatch",
                "candidate",
                "El estado embebido del candidato no coincide con la evaluación reproducida.",
            )

    candidate_consistent = None
    if provenance and architecture == "arm64":
        candidate_consistent = bool(
            candidate
            and candidate.get("schema") == CANDIDATE_SCHEMA
            and candidate.get("role") == "PHYSICAL_UAT_CANDIDATE_ONLY"
            and candidate.get("git_sha") == git_sha
            and candidate.get("architecture") == architecture
            and candidate.get("product_version") == provenance.get("product_version")
            and candidate.get("runtime_wave") == 76
            and isinstance(candidate_source_sha256, str)
            and len(candidate_source_sha256) == 64
        )
        if not candidate_consistent:
            _append_blocker(
                report,
                "physical_uat_candidate_manifest_missing_or_invalid",
                "uat",
                "El bundle arm64 no contiene un manifiesto W81 válido que identifique el candidato físico exacto.",
            )
        elif uat is not None and not uat_passed:
            if uat.get("git_sha") == git_sha and uat.get("candidate_source_sha256") != candidate_source_sha256:
                _append_blocker(
                    report,
                    "physical_uat_candidate_source_mismatch",
                    "uat",
                    "La evidencia UAT pertenece a una fuente distinta del candidato físico actual.",
                )
            if uat.get("git_sha") == git_sha and uat.get("candidate_manifest_sha256") != candidate_manifest_sha256:
                _append_blocker(
                    report,
                    "physical_uat_candidate_manifest_mismatch",
                    "uat",
                    "La evidencia UAT no coincide con el manifiesto exacto del candidato físico actual.",
                )

    report["app_evaluated"] = str(args.app.expanduser().resolve()) if args.app else None
    report["uat_evidence"] = str(args.uat_evidence.expanduser().resolve()) if args.uat_evidence else None
    report["provenance_schema"] = provenance.get("schema") if provenance else None
    report["embedded_readiness_schema"] = embedded.get("schema") if embedded else None
    report["candidate_schema"] = candidate.get("schema") if candidate else None
    report["candidate_source_sha256"] = candidate_source_sha256
    report["candidate_manifest_sha256"] = candidate_manifest_sha256
    report["candidate_manifest_consistent"] = candidate_consistent
    report["uat_schema"] = uat.get("schema") if uat else None
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if args.production:
        return 0 if report["production_ready"] else 2
    if args.expect_blocked:
        return 0 if not report["production_ready"] else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
