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
DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v2"
EXPECTED_RUNTIME_WAVE = 76
EXPECTED_GUARD_WAVE = 81
OPERATOR_HANDOFF_WAVE = 84
EXPECTED_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"


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


def _validate_candidate(app: Path, expected_git_sha: str) -> tuple[Path, dict[str, Any]]:
    resources = app / "Contents" / "Resources"
    manifest_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    if not manifest_path.is_file():
        raise ValueError(f"physical UAT candidate manifest missing: {manifest_path}")
    manifest = _json(manifest_path)
    if manifest.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError("unexpected physical UAT candidate schema")
    if manifest.get("role") != EXPECTED_ROLE:
        raise ValueError("bundle is not marked as a physical UAT candidate")
    if manifest.get("architecture") != "arm64":
        raise ValueError("current physical UAT delivery is arm64-only")
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
    if boundary.get("release_ready") is not False or boundary.get("release_tag") is not None:
        raise ValueError("candidate unexpectedly carries release authority")
    if boundary.get("production_ready") is not False:
        raise ValueError("candidate unexpectedly reports production-ready")
    physical = manifest.get("physical_uat") or {}
    if physical.get("required") is not True or physical.get("automatic_pass") is not False:
        raise ValueError("candidate physical UAT boundary drift")
    return manifest_path, manifest


def _operator_guide(*, git_sha: str, artifact: str, artifact_sha: str, handoff_archive: str, source_sha: str) -> str:
    return f"""# BINARIO Marketing IA · Physical UAT Operator Handoff

## Exact candidate

- Git SHA: `{git_sha}`
- Architecture: `arm64`
- Runtime: `Wave 76`
- Candidate guard: `Wave 81`
- Operator handoff: `Wave 84`
- Candidate source SHA-256: `{source_sha}`
- Candidate ZIP: `{artifact}`
- Candidate ZIP SHA-256: `{artifact_sha}`
- Permission-preserving handoff archive: `{handoff_archive}`
- Release authority: **NO**
- Automatic UAT pass: **NO**

## Start

From the downloaded GitHub Actions artifact, first expand `{handoff_archive}`. That inner archive is created with macOS `ditto` so the `.command` files retain executable permissions even if the outer Actions artifact normalizes file modes.

Inside the extracted handoff folder, double-click `START_PHYSICAL_UAT.command` on a real Apple Silicon Mac.
It verifies the candidate ZIP checksum, extracts the `.app`, verifies code-sign integrity, verifies the exact W81 candidate binding, initializes release-UAT evidence without passing any manual gate, and opens the app.

## Phase A · In-app physical product UAT

Use the guided physical-UAT panel in the app. Start an explicit session and execute the five required scenarios:

1. `company-switch`
2. `inbox-to-crm`
3. `pipeline-followup`
4. `campaign-execution`
5. `results-decision`

`optional-ai` is optional. Finish the session only after recording real observations. The in-app Release Evidence projection must accept that session for the current build (`accepted_for_current_build=true`).

## Phase B · Release operational UAT

Double-click `RECORD_RELEASE_UAT.command` once per manual gate. The command lists all 12 gates and their current status. Every recorded result requires `PASS` or `FAIL` plus a concrete observation note.

The 12 release gates cover launcher relaunch, persistence, company/CRM, Today completion, Today reschedule, content library, explicit social read-only refresh, manual reply, editorial management, real video import/render, embedded transcription, and credential/Keychain behavior.

## Non-negotiable boundary

A PASS in either phase does not change `RELEASE_READY`, create a tag, grant Developer ID signing, notarize the app, publish marketing, activate ads, or create release authority. Phase A and Phase B are separate evidence layers and neither may be inferred from the other.
"""


def package(app: Path, out_dir: Path, expected_git_sha: str) -> dict[str, Any]:
    app = app.expanduser().resolve()
    out_dir = out_dir.expanduser().resolve()
    if not app.is_dir():
        raise ValueError(f"app bundle missing: {app}")
    if len(expected_git_sha) != 40:
        raise ValueError("expected Git SHA must be a full 40-character commit SHA")

    manifest_path, manifest = _validate_candidate(app, expected_git_sha)
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
    guide_path = out_dir / "PHYSICAL_UAT_OPERATOR.md"

    ditto = Path("/usr/bin/ditto")
    if not ditto.is_file():
        raise ValueError("/usr/bin/ditto is required to package the macOS app")
    subprocess.run(
        [str(ditto), "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(zip_path)],
        check=True,
    )
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
    }
    for target, source in helper_sources.items():
        if not source.is_file():
            raise ValueError(f"operator handoff helper missing: {source}")
        shutil.copy2(source, target)
    starter_path.chmod(0o755)
    recorder_path.chmod(0o755)
    guide_path.write_text(
        _operator_guide(
            git_sha=expected_git_sha,
            artifact=zip_name,
            artifact_sha=artifact_sha,
            handoff_archive=handoff_name,
            source_sha=str(manifest.get("candidate_source_sha256") or ""),
        ),
        encoding="utf-8",
    )

    delivery = {
        "schema": DELIVERY_SCHEMA,
        "role": EXPECTED_ROLE,
        "product": manifest.get("product"),
        "git_sha": expected_git_sha,
        "architecture": "arm64",
        "product_version": manifest.get("product_version"),
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "operator_handoff_wave": OPERATOR_HANDOFF_WAVE,
        "operator_handoff_archive": handoff_name,
        "candidate_source_sha256": manifest.get("candidate_source_sha256"),
        "candidate_manifest_sha256": candidate_manifest_sha,
        "artifact": zip_name,
        "artifact_sha256": artifact_sha,
        "handoff_verifier_sha256": _sha256(verifier_path),
        "start_command_sha256": _sha256(starter_path),
        "record_command_sha256": _sha256(recorder_path),
        "operator_guide_sha256": _sha256(guide_path),
        "physical_uat_required": True,
        "physical_product_uat_required": True,
        "release_operational_uat_required": True,
        "automatic_uat_pass": False,
        "release_ready": False,
        "release_tag": None,
        "production_ready": False,
    }
    delivery_path.write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    staging = out_dir / f".physical-uat-handoff-{short_sha}"
    handoff_root = staging / f"BINARIO-PHYSICAL-UAT-{short_sha}"
    shutil.rmtree(staging, ignore_errors=True)
    handoff_root.mkdir(parents=True)
    handoff_members = (
        zip_path,
        checksum_path,
        delivery_path,
        external_manifest_path,
        external_summary_path,
        verifier_path,
        starter_path,
        recorder_path,
        guide_path,
    )
    for source in handoff_members:
        shutil.copy2(source, handoff_root / source.name)
    (handoff_root / starter_path.name).chmod(0o755)
    (handoff_root / recorder_path.name).chmod(0o755)
    subprocess.run(
        [str(ditto), "-c", "-k", "--sequesterRsrc", "--keepParent", str(handoff_root), str(handoff_path)],
        check=True,
    )
    handoff_sha = _sha256(handoff_path)
    handoff_checksum_path.write_text(f"{handoff_sha}  {handoff_name}\n", encoding="utf-8")
    shutil.rmtree(staging, ignore_errors=True)

    result = dict(delivery)
    result["operator_handoff_archive_sha256"] = handoff_sha
    print(json.dumps({"operator_handoff_archive": handoff_name, "sha256": handoff_sha}, ensure_ascii=False))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the exact current arm64 physical-UAT candidate and emit external delivery metadata.")
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
