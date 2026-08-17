#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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


def _uat_passed(path: Path | None, *, git_sha: str | None, architecture: str | None) -> tuple[bool, dict[str, Any] | None]:
    if path is None:
        return False, None
    data = _load_json(path)
    if data.get("schema") != "binario.marketing.release-uat-evidence.v1":
        return False, data
    if not git_sha or data.get("git_sha") != git_sha:
        return False, data
    if architecture and data.get("architecture") not in {architecture, "universal"}:
        return False, data
    return bool(data.get("uat_passed") is True and data.get("overall") == "UAT_PASS"), data


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate BINARIO Marketing release readiness without bypassing production gates.")
    ap.add_argument("--repo", type=Path, default=Path.cwd())
    ap.add_argument("--app", type=Path, help="Optional built .app candidate to evaluate.")
    ap.add_argument("--uat-evidence", type=Path, help="Optional physical UAT evidence bound to the candidate SHA.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--production", action="store_true", help="Exit non-zero unless the candidate is production ready.")
    mode.add_argument("--expect-blocked", action="store_true", help="Exit non-zero if the candidate is unexpectedly production ready.")
    args = ap.parse_args()

    repo = args.repo.expanduser().resolve()
    sys.path.insert(0, str(repo / "src"))
    from binario_marketing.release_readiness import evaluate_release_readiness

    provenance: dict[str, Any] | None = None
    embedded: dict[str, Any] | None = None
    signing_mode = notarized = git_sha = architecture = None
    source_kwargs: dict[str, Any] = {}
    if args.app:
        app = args.app.expanduser().resolve()
        resources = app / "Contents" / "Resources"
        provenance = _load_json(resources / "BUILD_PROVENANCE.json")
        embedded = _load_json(resources / "RELEASE_READINESS.json")
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
        uat_passed, uat = _uat_passed(args.uat_evidence, git_sha=git_sha, architecture=architecture)

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
            report["production_ready"] = False
            report["stage"] = "RELEASE_CANDIDATE_BLOCKED"
            if "embedded_state_mismatch" not in report["blocker_codes"]:
                report["blocker_codes"].append("embedded_state_mismatch")
                report["blockers"].append({"code": "embedded_state_mismatch", "scope": "candidate", "message": "El estado embebido del candidato no coincide con la evaluación reproducida."})
    report["app_evaluated"] = str(args.app.expanduser().resolve()) if args.app else None
    report["uat_evidence"] = str(args.uat_evidence.expanduser().resolve()) if args.uat_evidence else None
    report["provenance_schema"] = provenance.get("schema") if provenance else None
    report["embedded_readiness_schema"] = embedded.get("schema") if embedded else None
    report["uat_schema"] = uat.get("schema") if uat else None
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))

    if args.production:
        return 0 if report["production_ready"] else 2
    if args.expect_blocked:
        return 0 if not report["production_ready"] else 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
