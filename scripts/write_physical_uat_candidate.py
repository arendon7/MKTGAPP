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
CERTIFICATION_GUARD_WAVE = 84
REBUILD_SEMANTICS_WAVE = 88
RUNTIME_ENTRYPOINT = "service_wave76_app"
MANIFEST_NAME = "PHYSICAL_UAT_CANDIDATE.json"
SUMMARY_NAME = "PHYSICAL_UAT_CANDIDATE.md"
PHYSICAL_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"
DISTRIBUTION_ROLE = "DISTRIBUTION_REBUILD_ONLY"
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
    files: list[Path] = []
    for root in (source / "src", source / "web", source / "apps"):
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


def _origin_flags(event: str, ref: str) -> tuple[bool, bool]:
    physical = event == "push" and ref == "refs/heads/main"
    distribution = event == "push" and ref.startswith("refs/tags/v")
    return physical, distribution


def _role_for_origin(event: str, ref: str) -> str:
    physical, distribution = _origin_flags(event, ref)
    if physical:
        return PHYSICAL_ROLE
    if distribution:
        return DISTRIBUTION_ROLE
    return VALIDATION_ROLE


def _environment_origin() -> dict[str, Any]:
    event = str(os.environ.get("GITHUB_EVENT_NAME") or "local")
    ref = str(os.environ.get("GITHUB_REF") or "local")
    physical, distribution = _origin_flags(event, ref)
    return {
        "event": event,
        "ref": ref,
        "trusted_for_physical_uat": physical,
        "trusted_for_distribution_rebuild": distribution,
    }


def _validated_origin(origin: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(origin, dict):
        raise ValueError("candidate build origin must be an object")
    event = str(origin.get("event") or "local")
    ref = str(origin.get("ref") or "local")
    expected_physical, expected_distribution = _origin_flags(event, ref)
    physical = origin.get("trusted_for_physical_uat") is True
    distribution = origin.get("trusted_for_distribution_rebuild") is True
    if physical != expected_physical:
        raise ValueError("candidate physical-UAT build-origin trust mismatch")
    if distribution != expected_distribution:
        raise ValueError("candidate distribution rebuild-origin trust mismatch")
    if physical and distribution:
        raise ValueError("build origin cannot be both physical-UAT and distribution rebuild")
    return {
        "event": event,
        "ref": ref,
        "trusted_for_physical_uat": physical,
        "trusted_for_distribution_rebuild": distribution,
    }


def build_manifest(app: Path, *, build_origin: dict[str, Any] | None = None) -> dict[str, Any]:
    resources = app / "Contents/Resources"
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
    role = _role_for_origin(origin["event"], origin["ref"])
    physical_eligible = origin["trusted_for_physical_uat"]
    distribution_rebuild = origin["trusted_for_distribution_rebuild"]

    if provenance.get("architecture") != "arm64":
        raise ValueError(f"physical UAT/distribution handoff is arm64-only: {provenance.get('architecture')}")
    if provenance.get("product_version") != version:
        raise ValueError("candidate version/provenance mismatch")
    if f"service_wave{RUNTIME_WAVE}_app import serve" not in launch:
        raise ValueError(f"candidate runtime is not Wave {RUNTIME_WAVE}")
    if readiness.get("production_ready") is True:
        raise ValueError("embedded readiness unexpectedly reports production-ready before independent release gates")

    # Only the push-main artifact may become a new physical-UAT candidate. It must remain
    # development/fail-closed. A version-tag artifact is a distribution rebuild and may
    # eventually carry enabled release flags, but it can only inherit prior physical UAT
    # through W85/W86 exact source-equivalence evidence.
    if role == PHYSICAL_ROLE and (release_ready is not False or release_tag is not None):
        raise ValueError("physical UAT candidate must remain fail-closed for release")

    return {
        "schema": SCHEMA,
        "role": role,
        "product": "BINARIO Marketing IA",
        "git_sha": provenance.get("git_sha"),
        "architecture": "arm64",
        "product_version": version,
        "runtime_wave": RUNTIME_WAVE,
        "runtime_entrypoint": RUNTIME_ENTRYPOINT,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "rebuild_semantics_wave": REBUILD_SEMANTICS_WAVE,
        "build_origin": origin,
        "candidate_source_sha256": _source_digest(source),
        "hashes": {
            "build_provenance_sha256": _sha256(provenance_path),
            "embedded_readiness_sha256": _sha256(readiness_path),
            "launch_sha256": _sha256(launch_path),
        },
        "release_boundary": {
            "release_ready": bool(release_ready),
            "release_tag": release_tag,
            "production_ready": False,
            "version_is_development": ".dev" in version.lower(),
            "manifest_grants_release_authority": False,
        },
        "physical_uat": {
            "required": True,
            "automatic_pass": False,
            "eligible_architecture": "arm64",
            "eligible_build_origin": physical_eligible,
            "new_evidence_may_be_recorded": physical_eligible,
            "evidence_must_match_git_sha": True,
            "evidence_must_match_candidate_source_sha256": True,
            "source_equivalent_prior_evidence_allowed": distribution_rebuild,
        },
        "distribution_rebuild": {
            "eligible_build_origin": distribution_rebuild,
            "must_not_record_new_physical_uat": distribution_rebuild,
            "requires_prior_combined_uat_attestation": distribution_rebuild,
            "requires_distribution_trust_evidence": distribution_rebuild,
            "release_authority": False,
        },
        "sandbox_boundary": {
            "functional_sandbox_is_release_evidence": False,
            "synthetic_company_is_physical_uat_eligible": False,
        },
    }


def _summary(manifest: dict[str, Any]) -> str:
    origin = manifest["build_origin"]
    physical = manifest["physical_uat"]["eligible_build_origin"]
    distribution = manifest["distribution_rebuild"]["eligible_build_origin"]
    return "\n".join([
        "# BINARIO Marketing IA · Build Role Manifest",
        "",
        f"- Role: `{manifest['role']}`",
        f"- Git SHA: `{manifest['git_sha']}`",
        f"- Source SHA-256: `{manifest['candidate_source_sha256']}`",
        f"- Architecture: `{manifest['architecture']}`",
        f"- Product version: `{manifest['product_version']}`",
        f"- Runtime: Wave {manifest['runtime_wave']} (`{manifest['runtime_entrypoint']}`)",
        f"- Candidate guard: Wave {manifest['certification_guard_wave']}",
        f"- Rebuild semantics: Wave {manifest['rebuild_semantics_wave']}",
        f"- Build origin: `{origin['event']}` · `{origin['ref']}`",
        f"- Eligible to RECORD new physical UAT: **{'YES' if physical else 'NO'}**",
        f"- Eligible distribution rebuild origin: **{'YES' if distribution else 'NO'}**",
        "- Release authority from this manifest: **NO**",
        "- Automatic UAT PASS: **NO**",
        "",
        "Only a controlled push to refs/heads/main may record new physical-UAT evidence.",
        "A refs/tags/v* build is DISTRIBUTION_REBUILD_ONLY: it must not record a new physical UAT and may rely only on verified prior W85/W86 evidence bound by exact source equivalence.",
        "Pull-request, workflow-dispatch and local bundles are validation-only.",
        "Functional sandbox results are not physical release evidence.",
        "",
    ])


def write_manifest(app: Path) -> dict[str, Any]:
    manifest = build_manifest(app)
    resources = app / "Contents/Resources"
    (resources / MANIFEST_NAME).write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (resources / SUMMARY_NAME).write_text(_summary(manifest), encoding="utf-8")
    return manifest


def verify_manifest(app: Path) -> dict[str, Any]:
    resources = app / "Contents/Resources"
    path = resources / MANIFEST_NAME
    if not path.is_file():
        raise ValueError(f"candidate manifest missing: {path}")
    actual = _json(path)
    expected = build_manifest(app, build_origin=actual.get("build_origin"))
    if actual != expected:
        raise ValueError("physical UAT/build-role manifest drift")
    if not (resources / SUMMARY_NAME).is_file():
        raise ValueError("physical UAT/build-role summary missing")
    return actual


def main() -> int:
    parser = argparse.ArgumentParser()
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
