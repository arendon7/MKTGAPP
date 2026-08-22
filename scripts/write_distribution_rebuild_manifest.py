#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.distribution-rebuild.v1"
PURPOSE = "SOURCE_EQUIVALENT_DISTRIBUTION_REBUILD"
RUNTIME_WAVE = 76
RUNTIME_ENTRYPOINT = "service_wave76_app"
MANIFEST_NAME = "DISTRIBUTION_REBUILD.json"


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected JSON object: {path}")
    return data


def _source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for root in (source / "src", source / "web", source / "apps"):
        if not root.is_dir():
            raise ValueError(f"distribution source root missing: {root}")
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


def _origin() -> dict[str, Any]:
    event = str(os.environ.get("GITHUB_EVENT_NAME") or "local")
    ref = str(os.environ.get("GITHUB_REF") or "local")
    eligible = event == "push" and ref.startswith("refs/tags/v")
    return {"event": event, "ref": ref, "eligible_distribution_origin": eligible}


def build_manifest(app: Path, *, origin: dict[str, Any] | None = None) -> dict[str, Any]:
    resources = app / "Contents/Resources"
    source = resources / "source"
    provenance = _json(resources / "BUILD_PROVENANCE.json")
    launch = (resources / "launch.py").read_text(encoding="utf-8")
    version, release_ready, release_tag = _load_version(source)
    actual_origin = origin if origin is not None else _origin()
    event = str(actual_origin.get("event") or "local")
    ref = str(actual_origin.get("ref") or "local")
    eligible = actual_origin.get("eligible_distribution_origin") is True
    if eligible != (event == "push" and ref.startswith("refs/tags/v")):
        raise ValueError("distribution rebuild origin mismatch")
    if provenance.get("architecture") not in {"arm64", "x86_64"}:
        raise ValueError("distribution rebuild architecture unsupported")
    if provenance.get("product_version") != version:
        raise ValueError("distribution rebuild version/provenance mismatch")
    if f"service_wave{RUNTIME_WAVE}_app import serve" not in launch:
        raise ValueError(f"distribution rebuild runtime is not Wave {RUNTIME_WAVE}")
    if (resources / "PHYSICAL_UAT_CANDIDATE.json").exists() or (resources / "PHYSICAL_UAT_CANDIDATE.md").exists():
        raise ValueError("distribution rebuild must not contain physical-UAT candidate identity")
    return {
        "schema": SCHEMA,
        "purpose": PURPOSE,
        "git_sha": provenance.get("git_sha"),
        "architecture": provenance.get("architecture"),
        "product_version": version,
        "runtime_wave": RUNTIME_WAVE,
        "runtime_entrypoint": RUNTIME_ENTRYPOINT,
        "source_sha256": _source_digest(source),
        "build_origin": {"event": event, "ref": ref, "eligible_distribution_origin": eligible},
        "release_contract": {"release_ready": bool(release_ready), "release_tag": release_tag},
        "physical_uat": {"claimed": False, "exact_bundle_tested": False, "authorization_mode": "source_equivalent_only"},
        "release_authority": False,
    }


def write_manifest(app: Path) -> dict[str, Any]:
    manifest = build_manifest(app)
    path = app / "Contents/Resources" / MANIFEST_NAME
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify_manifest(app: Path) -> dict[str, Any]:
    path = app / "Contents/Resources" / MANIFEST_NAME
    if not path.is_file():
        raise ValueError(f"distribution rebuild manifest missing: {path}")
    actual = _json(path)
    expected = build_manifest(app, origin=actual.get("build_origin"))
    if actual != expected:
        raise ValueError("distribution rebuild manifest drift")
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
        "purpose": manifest["purpose"],
        "git_sha": manifest["git_sha"],
        "architecture": manifest["architecture"],
        "source_sha256": manifest["source_sha256"],
        "physical_uat_claimed": manifest["physical_uat"]["claimed"],
        "verified": bool(args.verify),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
