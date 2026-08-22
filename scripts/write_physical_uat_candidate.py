#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.physical-uat-candidate.v1"
RUNTIME_WAVE = 76
CERTIFICATION_GUARD_WAVE = 81
RUNTIME_ENTRYPOINT = "service_wave76_app"
MANIFEST_NAME = "PHYSICAL_UAT_CANDIDATE.json"
SUMMARY_NAME = "PHYSICAL_UAT_CANDIDATE.md"
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


def _source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    roots = [source / "src", source / "web", source / "apps"]
    files: list[Path] = []
    for root in roots:
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


def _load_version(source: Path) -> tuple[str, bool, str | None]:
    sys.path.insert(0, str(source / "src"))
    try:
        from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__
        return __version__, RELEASE_READY, RELEASE_TAG
    finally:
        try:
            sys.path.remove(str(source / "src"))
        except ValueError:
            pass


def _environment_origin() -> dict[str, Any]:
    event = str(os.environ.get("GITHUB_EVENT_NAME") or "local")
    ref = str(os.environ.get("GITHUB_REF") or "local")
    trusted = event == "push" and ref == "refs/heads/main"
    return {"event": event, "ref": ref, "trusted_for_physical_uat": trusted}


def _validated_origin(origin: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(origin, dict):
        raise ValueError("candidate build origin must be an object")
    event = str(origin.get("event") or "local")
    ref = str(origin.get("ref") or "local")
    trusted = origin.get("trusted_for_physical_uat") is True
    expected_trust = event == "push" and ref == "refs/heads/main"
    if trusted != expected_trust:
        raise ValueError("candidate build-origin trust mismatch")
    return {"event": event, "ref": ref, "trusted_for_physical_uat": trusted}


def build_manifest(app: Path, *, build_origin: dict[str, Any] | None = None) -> dict[str, Any]:
    resources = app / "Contents" / "Resources"
    source = resources / "source"
    provenance_path = resources / "BUILD_PROVENANCE.json"
    readiness_path = resources / "RELEASE_READINESS.json"
    launch_path = resources / "launch.py"
    for required in (provenance_path, readiness_path, launch_path):
        if not required.is_file():
            raise ValueError(f"candidate file missing: {required}")

    provenance = _json(provenance_path)
    readiness = _json(readiness_path)
    version, release_ready, release_tag = _load_version(source)
    launch = launch_path.read_text(encoding="utf-8")
    origin = _validated_origin(build_origin if build_origin is not None else _environment_origin())
    trusted_origin = origin["trusted_for_physical_uat"]

    if provenance.get("architecture") != "arm64":
        raise ValueError(f"physical UAT handoff is arm64-only: {provenance.get('architecture')}")
    if provenance.get("product_version") != version:
        raise ValueError("candidate version/provenance mismatch")
    if f"service_wave{RUNTIME_WAVE}_app import serve" not in launch:
        raise ValueError(f"candidate runtime is not Wave {RUNTIME_WAVE}")
    if release_ready is not False or release_tag is not None:
        raise ValueError("physical UAT candidate must remain fail-closed for release")
    if readiness.get("production_ready") is True:
        raise ValueError("embedded readiness unexpectedly reports production-ready")

    return {
        "schema": SCHEMA,
        "role": PHYSICAL_ROLE if trusted_origin else VALIDATION_ROLE,
        "product": "BINARIO Marketing IA",
        "git_sha": provenance.get("git_sha"),
        "architecture": "arm64",
        "product_version": version,
        "runtime_wave": RUNTIME_WAVE,
        "runtime_entrypoint": RUNTIME_ENTRYPOINT,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "build_origin": origin,
        "candidate_source_sha256": _source_digest(source),
        "hashes": {
            "build_provenance_sha256": _sha256(provenance_path),
            "embedded_readiness_sha256": _sha256(readiness_path),
            "launch_sha256": _sha256(launch_path),
        },
        "release_boundary": {
            "release_ready": False,
            "release_tag": None,
            "production_ready": False,
            "version_is_development": ".dev" in version.lower(),
        },
        "physical_uat": {
            "required": True,
            "automatic_pass": False,
            "eligible_architecture": "arm64",
            "eligible_build_origin": trusted_origin,
            "evidence_must_match_git_sha": True,
            "evidence_must_match_candidate_source_sha256": True,
        },
        "sandbox_boundary": {
            "functional_sandbox_is_release_evidence": False,
            "synthetic_company_is_physical_uat_eligible": False,
        },
    }


def _summary(manifest: dict[str, Any]) -> str:
    origin = manifest["build_origin"]
    eligible = manifest["physical_uat"]["eligible_build_origin"]
    return "\n".join(
        [
            "# BINARIO Marketing IA · Physical UAT Candidate",
            "",
            f"- Role: `{manifest['role']}`",
            f"- Git SHA: `{manifest['git_sha']}`",
            f"- Source SHA-256: `{manifest['candidate_source_sha256']}`",
            f"- Architecture: `{manifest['architecture']}`",
            f"- Product version: `{manifest['product_version']}`",
            f"- Runtime: Wave {manifest['runtime_wave']} (`{manifest['runtime_entrypoint']}`)",
            f"- Certification guard: Wave {manifest['certification_guard_wave']}",
            f"- Build origin: `{origin['event']}` · `{origin['ref']}`",
            f"- Eligible physical-UAT origin: **{'YES' if eligible else 'NO'}**",
            "- Release authority: **NO**",
            "- Physical UAT required: **YES**",
            "- Automatic PASS: **NO**",
            "",
            "Only an arm64 bundle produced by a GitHub Actions push to refs/heads/main is an eligible physical-UAT candidate.",
            "Pull-request, local and workflow-dispatch bundles are validation artifacts only and must not record physical-UAT evidence.",
            "Functional sandbox results are not physical release evidence.",
            "Any physical UAT evidence must match both this Git SHA and the candidate source SHA-256.",
            "",
        ]
    )


def write_manifest(app: Path) -> dict[str, Any]:
    manifest = build_manifest(app)
    resources = app / "Contents" / "Resources"
    (resources / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (resources / SUMMARY_NAME).write_text(_summary(manifest), encoding="utf-8")
    return manifest


def verify_manifest(app: Path) -> dict[str, Any]:
    resources = app / "Contents" / "Resources"
    manifest_path = resources / MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"candidate manifest missing: {manifest_path}")
    actual = _json(manifest_path)
    expected = build_manifest(app, build_origin=actual.get("build_origin"))
    if actual != expected:
        raise ValueError("physical UAT candidate manifest drift")
    summary = resources / SUMMARY_NAME
    if not summary.is_file():
        raise ValueError("physical UAT candidate summary missing")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser(description="Write or verify an exact physical-UAT candidate manifest inside a BINARIO Marketing .app bundle.")
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    app = args.app.expanduser().resolve()
    manifest = verify_manifest(app) if args.verify else write_manifest(app)
    print(json.dumps({
        "schema": manifest["schema"],
        "role": manifest["role"],
        "git_sha": manifest["git_sha"],
        "candidate_source_sha256": manifest["candidate_source_sha256"],
        "runtime_wave": manifest["runtime_wave"],
        "architecture": manifest["architecture"],
        "build_origin": manifest["build_origin"],
        "verified": bool(args.verify),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
