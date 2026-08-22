#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v3"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 84
OPERATOR_HANDOFF_WAVE = 85
DUAL_EVIDENCE_GUARD_WAVE = 85
PHYSICAL_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"
VALIDATION_ROLE = "VALIDATION_BUILD_ONLY"


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _trusted_origin(manifest: dict[str, Any]) -> bool:
    origin = manifest.get("build_origin") if isinstance(manifest.get("build_origin"), dict) else {}
    ref = str(origin.get("ref") or "")
    return bool(origin.get("event") == "push" and (ref == "refs/heads/main" or ref.startswith("refs/tags/v")) and origin.get("trusted_for_physical_uat") is True)


def _validate_candidate(app: Path, expected_git_sha: str) -> tuple[Path, dict[str, Any], bool]:
    resources = app / "Contents" / "Resources"
    manifest_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    if not manifest_path.is_file():
        raise ValueError(f"physical UAT candidate manifest missing: {manifest_path}")
    manifest = _json(manifest_path)
    trusted = _trusted_origin(manifest)
    expected_role = PHYSICAL_ROLE if trusted else VALIDATION_ROLE
    if manifest.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError("unexpected physical UAT candidate schema")
    if manifest.get("role") != expected_role:
        raise ValueError("candidate role/build-origin mismatch")
    if manifest.get("architecture") != "arm64":
        raise ValueError("current arm64 delivery is arm64-only")
    if manifest.get("runtime_wave") != EXPECTED_RUNTIME_WAVE:
        raise ValueError("candidate runtime wave drift")
    if manifest.get("certification_guard_wave") != EXPECTED_GUARD_WAVE:
        raise ValueError("candidate certification guard drift")
    if manifest.get("git_sha") != expected_git_sha:
        raise ValueError(f"candidate git SHA mismatch: {manifest.get('git_sha')} != {expected_git_sha}")
    source_sha = str(manifest.get("candidate_source_sha256") or "")
    if len(source_sha) != 64:
        raise ValueError("candidate source SHA-256 missing or malformed")
    boundary = manifest.get("release_boundary") or {}
    if boundary.get("release_ready") is not False or boundary.get("release_tag") is not None or boundary.get("production_ready") is not False:
        raise ValueError("candidate unexpectedly carries release authority")
    physical = manifest.get("physical_uat") or {}
    if physical.get("required") is not True or physical.get("automatic_pass") is not False:
        raise ValueError("candidate physical UAT boundary drift")
    if physical.get("eligible_build_origin") is not trusted:
        raise ValueError("candidate physical UAT origin eligibility drift")
    return manifest_path, manifest, trusted


def _operator_guide(*, git_sha: str, artifact: str, artifact_sha: str, handoff_archive: str, source_sha: str, role: str, eligible: bool) -> str:
    return f"""# BINARIO Marketing IA · Physical UAT Operator Handoff

## Exact build
- Role: `{role}`
- Physical-UAT eligible: **{'YES' if eligible else 'NO'}**
- Git SHA: `{git_sha}`
- Architecture: `arm64`
- Runtime: `Wave 76`
- Candidate guard: `Wave 84`
- Dual evidence guard / operator handoff: `Wave 85`
- Candidate source SHA-256: `{source_sha}`
- Candidate ZIP: `{artifact}`
- Candidate ZIP SHA-256: `{artifact_sha}`
- Permission-preserving handoff archive: `{handoff_archive}`
- Release authority: **NO**
- Automatic UAT pass: **NO**

## Start
A PR build may be fully audited but remains validation-only. `START_PHYSICAL_UAT.command` proceeds only for `PHYSICAL_UAT_CANDIDATE_ONLY` from controlled `push` on main or a version tag.

## Phase A · Product UAT
Run the five required in-app scenarios and finish the session. Then run `COLLECT_PRODUCT_UAT.command`; it exports `product-uat-evidence.json` only when the session PASS, machine, session digest, Git SHA, version, source digest and candidate manifest are exact.

## Phase B · Release operational UAT
Use `RECORD_RELEASE_UAT.command` for the 12 manual release gates. Every result requires PASS/FAIL plus a concrete note.

## Dual gate
`release_candidate_gate.py` treats UAT as passed only when Phase A and Phase B both PASS and bind to the same Git SHA, candidate source SHA-256 and candidate manifest SHA-256.

Neither phase changes `RELEASE_READY`, creates tags, grants Developer ID signing, notarizes the app, publishes marketing or activates ads.
"""


def package(app: Path, out_dir: Path, expected_git_sha: str) -> dict[str, Any]:
    app = app.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    if not app.is_dir():
        raise ValueError(f"app bundle missing: {app}")
    if len(expected_git_sha) != 40:
        raise ValueError("expected Git SHA must be a full 40-character commit SHA")
    manifest_path, manifest, trusted = _validate_candidate(app, expected_git_sha)
    summary_path = app / "Contents" / "Resources" / "PHYSICAL_UAT_CANDIDATE.md"
    if not summary_path.is_file():
        raise ValueError(f"physical UAT candidate summary missing: {summary_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    short_sha = expected_git_sha[:12]
    zip_name = f"Binario-Marketing-IA-PHYSICAL-UAT-arm64-{short_sha}.zip"
    zip_path = out_dir / zip_name
    checksum_path = out_dir / f"{zip_name}.sha256"
    handoff_name = f"Binario-Marketing-IA-PHYSICAL-UAT-arm64-HANDOFF-{short_sha}.zip"
    handoff_path = out_dir / handoff_name
    handoff_checksum_path = out_dir / f"{handoff_name}.sha256"
    delivery_path = out_dir / "FULL_MAC_DELIVERY.json"
    external_manifest_path = out_dir / "PHYSICAL_UAT_CANDIDATE.json"
    external_summary_path = out_dir / "PHYSICAL_UAT_CANDIDATE.md"
    verifier_path = out_dir / "PHYSICAL_UAT_HANDOFF_VERIFY.py"
    starter_path = out_dir / "START_PHYSICAL_UAT.command"
    recorder_path = out_dir / "RECORD_RELEASE_UAT.command"
    product_collector_path = out_dir / "PRODUCT_UAT_COLLECT.py"
    product_command_path = out_dir / "COLLECT_PRODUCT_UAT.command"
    guide_path = out_dir / "PHYSICAL_UAT_OPERATOR.md"

    ditto = Path("/usr/bin/ditto")
    if not ditto.is_file():
        raise ValueError("/usr/bin/ditto is required to package the macOS app")
    subprocess.run([str(ditto), "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(zip_path)], check=True)
    artifact_sha = _sha256(zip_path)
    candidate_manifest_sha = _sha256(manifest_path)
    checksum_path.write_text(f"{artifact_sha}  {zip_name}\n", encoding="utf-8")
    shutil.copy2(manifest_path, external_manifest_path)
    shutil.copy2(summary_path, external_summary_path)

    scripts = Path(__file__).resolve().parent
    helper_sources = {
        verifier_path: scripts / "verify_physical_uat_handoff.py",
        starter_path: scripts / "start_physical_uat.command",
        recorder_path: scripts / "record_release_uat.command",
        product_collector_path: scripts / "collect_product_uat.py",
        product_command_path: scripts / "collect_product_uat.command",
    }
    for target, source in helper_sources.items():
        if not source.is_file():
            raise ValueError(f"operator handoff helper missing: {source}")
        shutil.copy2(source, target)
    starter_path.chmod(0o755)
    recorder_path.chmod(0o755)
    product_command_path.chmod(0o755)
    guide_path.write_text(_operator_guide(git_sha=expected_git_sha, artifact=zip_name, artifact_sha=artifact_sha, handoff_archive=handoff_name, source_sha=str(manifest.get("candidate_source_sha256") or ""), role=str(manifest.get("role") or ""), eligible=trusted), encoding="utf-8")

    delivery = {
        "schema": DELIVERY_SCHEMA,
        "role": manifest.get("role"),
        "product": manifest.get("product"),
        "git_sha": expected_git_sha,
        "architecture": "arm64",
        "product_version": manifest.get("product_version"),
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "operator_handoff_wave": OPERATOR_HANDOFF_WAVE,
        "dual_evidence_guard_wave": DUAL_EVIDENCE_GUARD_WAVE,
        "operator_handoff_archive": handoff_name,
        "build_origin": manifest.get("build_origin"),
        "candidate_source_sha256": manifest.get("candidate_source_sha256"),
        "candidate_manifest_sha256": candidate_manifest_sha,
        "artifact": zip_name,
        "artifact_sha256": artifact_sha,
        "handoff_verifier_sha256": _sha256(verifier_path),
        "start_command_sha256": _sha256(starter_path),
        "record_command_sha256": _sha256(recorder_path),
        "product_uat_collector_sha256": _sha256(product_collector_path),
        "product_uat_command_sha256": _sha256(product_command_path),
        "operator_guide_sha256": _sha256(guide_path),
        "physical_uat_eligible": trusted,
        "physical_uat_required": True,
        "physical_product_uat_required": True,
        "release_operational_uat_required": True,
        "dual_physical_uat_required": True,
        "automatic_uat_pass": False,
        "release_ready": False,
        "release_tag": None,
        "production_ready": False,
    }
    delivery_path.write_text(json.dumps(delivery, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    staging = out_dir / f".physical-uat-handoff-{short_sha}"
    handoff_root = staging / f"BINARIO-PHYSICAL-UAT-{short_sha}"
    shutil.rmtree(staging, ignore_errors=True)
    handoff_root.mkdir(parents=True)
    handoff_members = (zip_path, checksum_path, delivery_path, external_manifest_path, external_summary_path, verifier_path, starter_path, recorder_path, product_collector_path, product_command_path, guide_path)
    for source in handoff_members:
        shutil.copy2(source, handoff_root / source.name)
    for command in (starter_path.name, recorder_path.name, product_command_path.name):
        (handoff_root / command).chmod(0o755)
    subprocess.run([str(ditto), "-c", "-k", "--sequesterRsrc", "--keepParent", str(handoff_root), str(handoff_path)], check=True)
    handoff_sha = _sha256(handoff_path)
    handoff_checksum_path.write_text(f"{handoff_sha}  {handoff_name}\n", encoding="utf-8")
    shutil.rmtree(staging, ignore_errors=True)
    result = dict(delivery)
    result["operator_handoff_archive_sha256"] = handoff_sha
    print(json.dumps({"operator_handoff_archive": handoff_name, "sha256": handoff_sha}, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA"))
    args = parser.parse_args()
    if not args.git_sha:
        raise SystemExit("--git-sha or GITHUB_SHA is required")
    try:
        delivery = package(args.app, args.out, str(args.git_sha))
    except (ValueError, subprocess.CalledProcessError) as exc:
        raise SystemExit(f"CURRENT ARM64 CANDIDATE PACKAGE BLOCKED: {exc}") from exc
    print(json.dumps(delivery, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
