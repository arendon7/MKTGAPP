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
    resources = app / "Contents/Resources"
    manifest_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
    if not manifest_path.is_file():
        raise ValueError(f"physical UAT candidate manifest missing: {manifest_path}")
    manifest = _json(manifest_path)
    if manifest.get("schema") != CANDIDATE_SCHEMA:
        raise ValueError("unexpected physical UAT candidate schema")
    trusted = _trusted_origin(manifest)
    expected_role = PHYSICAL_ROLE if trusted else VALIDATION_ROLE
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


def package(app: Path, out_dir: Path, expected_git_sha: str) -> dict[str, Any]:
    app = app.expanduser().resolve(); out_dir = out_dir.expanduser().resolve()
    if not app.is_dir(): raise ValueError(f"app bundle missing: {app}")
    if len(expected_git_sha) != 40: raise ValueError("expected Git SHA must be a full 40-character commit SHA")
    manifest_path, manifest, trusted = _validate_candidate(app, expected_git_sha)
    summary_path = app / "Contents/Resources/PHYSICAL_UAT_CANDIDATE.md"
    if not summary_path.is_file(): raise ValueError(f"physical UAT candidate summary missing: {summary_path}")
    out_dir.mkdir(parents=True, exist_ok=True)
    short_sha = expected_git_sha[:12]
    prefix = "Binario-Marketing-IA-PHYSICAL-UAT-arm64" if trusted else "Binario-Marketing-IA-VALIDATION-arm64"
    zip_name = f"{prefix}-{short_sha}.zip"
    zip_path = out_dir / zip_name
    checksum_path = out_dir / f"{zip_name}.sha256"
    delivery_path = out_dir / "FULL_MAC_DELIVERY.json"
    external_manifest_path = out_dir / "PHYSICAL_UAT_CANDIDATE.json"
    external_summary_path = out_dir / "PHYSICAL_UAT_CANDIDATE.md"
    ditto = Path("/usr/bin/ditto")
    if not ditto.is_file(): raise ValueError("/usr/bin/ditto is required to package the macOS app")
    subprocess.run([str(ditto), "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(zip_path)], check=True)
    artifact_sha = _sha256(zip_path); candidate_manifest_sha = _sha256(manifest_path)
    checksum_path.write_text(f"{artifact_sha}  {zip_name}\n", encoding="utf-8")
    shutil.copy2(manifest_path, external_manifest_path); shutil.copy2(summary_path, external_summary_path)
    delivery = {
        "schema": DELIVERY_SCHEMA,
        "role": manifest.get("role"),
        "product": manifest.get("product"),
        "git_sha": expected_git_sha,
        "architecture": "arm64",
        "product_version": manifest.get("product_version"),
        "runtime_wave": EXPECTED_RUNTIME_WAVE,
        "certification_guard_wave": EXPECTED_GUARD_WAVE,
        "build_origin": manifest.get("build_origin"),
        "candidate_source_sha256": manifest.get("candidate_source_sha256"),
        "candidate_manifest_sha256": candidate_manifest_sha,
        "artifact": zip_name,
        "artifact_sha256": artifact_sha,
        "physical_uat_eligible": trusted,
        "physical_uat_required": True,
        "automatic_uat_pass": False,
        "release_ready": False,
        "release_tag": None,
        "production_ready": False,
    }
    delivery_path.write_text(json.dumps(delivery, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return delivery


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the exact current arm64 build with explicit validation/physical-UAT role.")
    parser.add_argument("--app", type=Path, required=True); parser.add_argument("--out", type=Path, default=Path(".")); parser.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA"))
    args = parser.parse_args()
    if not args.git_sha: raise SystemExit("--git-sha or GITHUB_SHA is required")
    try: delivery = package(args.app, args.out, str(args.git_sha))
    except (ValueError, subprocess.CalledProcessError) as exc: raise SystemExit(f"CURRENT ARM64 CANDIDATE PACKAGE BLOCKED: {exc}") from exc
    print(json.dumps(delivery, ensure_ascii=False, indent=2, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
