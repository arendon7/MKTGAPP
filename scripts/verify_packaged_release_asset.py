#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "binario.marketing.post-package-trust.v1"
RUNTIME_WAVE = 76
CERTIFICATION_GUARD_WAVE = 92
EXPECTED_ARCHITECTURES = {"arm64", "x86_64"}
APP_NAME = "Binario Marketing IA.app"
DISTRIBUTION_REBUILD_SCHEMA = "binario.marketing.distribution-rebuild.v1"
DISTRIBUTION_REBUILD_PURPOSE = "SOURCE_EQUIVALENT_DISTRIBUTION_REBUILD"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON evidence: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"JSON evidence must be an object: {path}")
    return data


def _sha256_file(path: Path) -> str:
    _require(path.is_file(), f"file missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    core = dict(payload)
    core.pop("evidence_sha256", None)
    result = dict(core)
    result["evidence_sha256"] = _digest(core)
    return result


def _verify_seal(payload: dict[str, Any]) -> None:
    expected = str(payload.get("evidence_sha256") or "")
    _require(len(expected) == 64, "post-package evidence digest missing or malformed")
    core = dict(payload)
    core.pop("evidence_sha256", None)
    _require(_digest(core) == expected, "post-package evidence digest mismatch")


def _source_digest(source: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for root in (source / "src", source / "web", source / "apps"):
        _require(root.is_dir(), f"distribution source root missing: {root}")
        files.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(source).as_posix()):
        relative = path.relative_to(source).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _validate_archive_inventory(asset: Path) -> dict[str, Any]:
    _require(asset.is_file(), f"release ZIP missing: {asset}")
    try:
        with zipfile.ZipFile(asset, "r") as archive:
            infos = archive.infolist()
    except (OSError, zipfile.BadZipFile) as exc:
        raise ValueError(f"invalid release ZIP: {asset}: {exc}") from exc
    _require(bool(infos), "release ZIP is empty")
    real_app_entries = 0
    for info in infos:
        name = info.filename
        _require(bool(name), "release ZIP contains an unnamed entry")
        _require("\\" not in name, f"release ZIP contains non-canonical path separator: {name}")
        _require(not name.startswith("/"), f"release ZIP contains absolute path: {name}")
        parts = PurePosixPath(name).parts
        _require(bool(parts), f"release ZIP contains invalid path: {name}")
        _require(".." not in parts and "." not in parts, f"release ZIP contains path traversal: {name}")
        root = parts[0]
        if root == APP_NAME:
            real_app_entries += 1
            continue
        if root == "__MACOSX":
            _require(len(parts) >= 2, "release ZIP contains bare __MACOSX entry")
            second = parts[1]
            _require(
                second in {APP_NAME, f"._{APP_NAME}"},
                f"release ZIP contains metadata outside canonical app root: {name}",
            )
            continue
        raise ValueError(f"release ZIP contains unexpected top-level content: {name}")
    _require(real_app_entries > 0, f"release ZIP does not contain {APP_NAME}")
    return {
        "entry_count": len(infos),
        "canonical_app_root": APP_NAME,
        "path_safety_verified": True,
        "single_product_root_verified": True,
    }


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(command, check=True, text=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or exc.stdout or "").strip()
        else:
            detail = str(exc)
        raise ValueError(f"command failed: {' '.join(command)}: {detail}") from exc


def _developer_id_identity(app: Path) -> str:
    result = _run(["/usr/bin/codesign", "-dv", "--verbose=4", str(app)])
    text = "\n".join(part for part in (result.stdout, result.stderr) if part)
    matches = re.findall(r"^Authority=(Developer ID Application:.+)$", text, flags=re.MULTILINE)
    _require(len(matches) == 1, "extracted app does not expose exactly one Developer ID Application authority")
    return matches[0].strip()


def _verify_distribution_trust(path: Path, *, git_sha: str, architecture: str, product_version: str) -> tuple[dict[str, Any], dict[str, Any]]:
    scripts = Path(__file__).resolve().parent
    sys.path.insert(0, str(scripts))
    try:
        from verify_distribution_trust import verify
        report = verify(path, git_sha=git_sha, architecture=architecture, product_version=product_version)
    finally:
        try:
            sys.path.remove(str(scripts))
        except ValueError:
            pass
    raw = _load_json(path)
    return report, raw


def build_roundtrip_evidence(
    *,
    asset: Path,
    distribution_evidence: Path,
    tag: str,
    architecture: str,
    expected_git_sha: str,
) -> dict[str, Any]:
    asset = asset.expanduser().resolve()
    distribution_evidence = distribution_evidence.expanduser().resolve()
    _require(platform.system() == "Darwin", "post-package round-trip trust must execute on macOS")
    _require(architecture in EXPECTED_ARCHITECTURES, "unsupported release architecture")
    _require(len(expected_git_sha) == 40, "expected git SHA missing or malformed")
    archive = _validate_archive_inventory(asset)

    with tempfile.TemporaryDirectory(prefix="binario-post-package-") as raw:
        extracted_root = Path(raw)
        _run(["/usr/bin/ditto", "-x", "-k", str(asset), str(extracted_root)])
        app = extracted_root / APP_NAME
        _require(app.is_dir(), f"round-trip extraction did not produce {APP_NAME}")
        resources = app / "Contents/Resources"
        provenance_path = resources / "BUILD_PROVENANCE.json"
        readiness_path = resources / "RELEASE_READINESS.json"
        rebuild_path = resources / "DISTRIBUTION_REBUILD.json"
        provenance = _load_json(provenance_path)
        readiness = _load_json(readiness_path)
        rebuild = _load_json(rebuild_path)

        git_sha = str(provenance.get("git_sha") or "")
        product_version = str(provenance.get("product_version") or "")
        _require(git_sha == expected_git_sha, "round-trip app git SHA mismatch")
        _require(provenance.get("architecture") == architecture, "round-trip app architecture mismatch")
        _require(bool(product_version), "round-trip app product version missing")
        _require(tag == f"v{product_version}", "round-trip app tag/version mismatch")
        _require(provenance.get("signing_mode") == "developer_id", "round-trip app provenance is not Developer ID signed")
        _require(readiness.get("git_sha") == git_sha, "round-trip readiness git SHA mismatch")
        _require(readiness.get("architecture") == architecture, "round-trip readiness architecture mismatch")
        _require(readiness.get("version") == product_version, "round-trip readiness version mismatch")
        _require(readiness.get("release_ready_flag") is True, "round-trip readiness release flag is false")
        _require(readiness.get("release_tag") == tag, "round-trip readiness release tag mismatch")
        _require(rebuild.get("schema") == DISTRIBUTION_REBUILD_SCHEMA, "round-trip rebuild schema mismatch")
        _require(rebuild.get("purpose") == DISTRIBUTION_REBUILD_PURPOSE, "round-trip rebuild purpose mismatch")
        _require(rebuild.get("git_sha") == git_sha, "round-trip rebuild git SHA mismatch")
        _require(rebuild.get("architecture") == architecture, "round-trip rebuild architecture mismatch")
        _require(rebuild.get("product_version") == product_version, "round-trip rebuild version mismatch")
        _require(rebuild.get("runtime_wave") == RUNTIME_WAVE, "round-trip rebuild runtime wave drift")
        _require(rebuild.get("release_authority") is False, "round-trip rebuild improperly carries release authority")
        _require(not (resources / "PHYSICAL_UAT_CANDIDATE.json").exists(), "distribution ZIP contains physical-UAT candidate identity")
        _require(not (resources / "PHYSICAL_UAT_CANDIDATE.md").exists(), "distribution ZIP contains physical-UAT candidate handoff")
        source_sha256 = _source_digest(resources / "source")
        _require(rebuild.get("source_sha256") == source_sha256, "round-trip source digest mismatch")

        trust, raw_trust = _verify_distribution_trust(
            distribution_evidence,
            git_sha=git_sha,
            architecture=architecture,
            product_version=product_version,
        )
        expected_identity = str(raw_trust.get("developer_id_identity") or "")
        _require(expected_identity.startswith("Developer ID Application:"), "distribution trust Developer ID identity missing")

        _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", "--verbose=2", str(app)])
        actual_identity = _developer_id_identity(app)
        _require(actual_identity == expected_identity, "round-trip Developer ID identity differs from notarized distribution trust")
        _run(["/usr/bin/xcrun", "stapler", "validate", str(app)])
        _run(["/usr/sbin/spctl", "--assess", "--type", "execute", "--verbose=4", str(app)])

        payload = {
            "schema": SCHEMA,
            "tag": tag,
            "git_sha": git_sha,
            "architecture": architecture,
            "product_version": product_version,
            "runtime_wave": RUNTIME_WAVE,
            "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
            "source_sha256": source_sha256,
            "asset": {
                "name": asset.name,
                "sha256": _sha256_file(asset),
                "size_bytes": asset.stat().st_size,
            },
            "archive": archive,
            "extracted_app": {
                "bundle_name": APP_NAME,
                "build_provenance_sha256": _sha256_file(provenance_path),
                "release_readiness_sha256": _sha256_file(readiness_path),
                "distribution_rebuild_manifest_sha256": _sha256_file(rebuild_path),
            },
            "pre_package_distribution_trust": {
                "schema": trust.get("schema"),
                "evidence_file_sha256": _sha256_file(distribution_evidence),
                "evidence_sha256": trust.get("evidence_sha256"),
                "developer_id_identity": expected_identity,
                "notary_submission_id": trust.get("notary_submission_id"),
            },
            "roundtrip_trust": {
                "codesign_verified": True,
                "developer_id_identity": actual_identity,
                "stapler_validated": True,
                "gatekeeper_assessed": True,
            },
            "asset_roundtrip_verified": True,
            "operational_authorization": False,
            "release_authority": False,
            "publication_authority": False,
            "production_ready": False,
            "mutations_performed": False,
        }
        return _seal(payload)


def verify_evidence(
    evidence_path: Path,
    *,
    asset: Path,
    distribution_evidence: Path,
    expected_tag: str | None = None,
    expected_git_sha: str | None = None,
    expected_architecture: str | None = None,
) -> dict[str, Any]:
    evidence_path = evidence_path.expanduser().resolve()
    asset = asset.expanduser().resolve()
    distribution_evidence = distribution_evidence.expanduser().resolve()
    data = _load_json(evidence_path)
    _require(data.get("schema") == SCHEMA, "unexpected post-package trust schema")
    _verify_seal(data)
    _require(data.get("runtime_wave") == RUNTIME_WAVE, "post-package trust runtime wave drift")
    _require(data.get("certification_guard_wave") == CERTIFICATION_GUARD_WAVE, "post-package trust guard wave drift")
    _require(data.get("architecture") in EXPECTED_ARCHITECTURES, "unsupported post-package architecture")
    if expected_tag is not None:
        _require(data.get("tag") == expected_tag, "post-package trust tag mismatch")
    if expected_git_sha is not None:
        _require(data.get("git_sha") == expected_git_sha, "post-package trust git SHA mismatch")
    if expected_architecture is not None:
        _require(data.get("architecture") == expected_architecture, "post-package trust architecture mismatch")
    _require(data.get("tag") == f"v{data.get('product_version')}", "post-package trust tag/version mismatch")

    asset_row = data.get("asset") or {}
    _require(asset.is_file(), f"release asset missing: {asset}")
    _require(asset.name == asset_row.get("name"), "post-package trust asset filename mismatch")
    _require(_sha256_file(asset) == asset_row.get("sha256"), "post-package trust asset digest mismatch")
    _require(asset.stat().st_size == asset_row.get("size_bytes"), "post-package trust asset size mismatch")

    raw_trust = _load_json(distribution_evidence)
    pre = data.get("pre_package_distribution_trust") or {}
    _require(_sha256_file(distribution_evidence) == pre.get("evidence_file_sha256"), "post-package trust distribution evidence bytes mismatch")
    _require(raw_trust.get("evidence_sha256") == pre.get("evidence_sha256"), "post-package trust distribution evidence digest mismatch")
    _require(raw_trust.get("developer_id_identity") == pre.get("developer_id_identity"), "post-package trust Developer ID identity mismatch")
    _require(raw_trust.get("notary_submission_id") == pre.get("notary_submission_id"), "post-package trust notary submission mismatch")
    _require(raw_trust.get("git_sha") == data.get("git_sha"), "post-package trust distribution git SHA mismatch")
    _require(raw_trust.get("architecture") == data.get("architecture"), "post-package trust distribution architecture mismatch")
    _require(raw_trust.get("product_version") == data.get("product_version"), "post-package trust distribution version mismatch")

    archive = data.get("archive") or {}
    roundtrip = data.get("roundtrip_trust") or {}
    _require(archive.get("path_safety_verified") is True, "post-package archive path safety is not verified")
    _require(archive.get("single_product_root_verified") is True, "post-package archive root is not verified")
    _require(roundtrip.get("codesign_verified") is True, "round-trip codesign verification missing")
    _require(str(roundtrip.get("developer_id_identity") or "").startswith("Developer ID Application:"), "round-trip Developer ID identity missing")
    _require(roundtrip.get("developer_id_identity") == pre.get("developer_id_identity"), "round-trip Developer ID identity drift")
    _require(roundtrip.get("stapler_validated") is True, "round-trip stapler validation missing")
    _require(roundtrip.get("gatekeeper_assessed") is True, "round-trip Gatekeeper assessment missing")
    _require(data.get("asset_roundtrip_verified") is True, "release asset did not pass round-trip verification")
    _require(data.get("operational_authorization") is False, "post-package evidence must not carry operational authorization")
    _require(data.get("release_authority") is False, "post-package evidence must not carry release authority")
    _require(data.get("publication_authority") is False, "post-package evidence must not carry publication authority")
    _require(data.get("production_ready") is False, "post-package evidence must not claim production readiness")
    _require(data.get("mutations_performed") is False, "post-package verification must not claim publication mutations")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify the exact packaged BINARIO macOS ZIP by round-trip extraction and Apple trust checks.")
    sub = parser.add_subparsers(dest="command", required=True)

    roundtrip = sub.add_parser("roundtrip")
    roundtrip.add_argument("--asset", type=Path, required=True)
    roundtrip.add_argument("--distribution-evidence", type=Path, required=True)
    roundtrip.add_argument("--tag", required=True)
    roundtrip.add_argument("--architecture", choices=sorted(EXPECTED_ARCHITECTURES), required=True)
    roundtrip.add_argument("--expected-git-sha", required=True)
    roundtrip.add_argument("--output", type=Path, required=True)

    verify = sub.add_parser("verify-evidence")
    verify.add_argument("--evidence", type=Path, required=True)
    verify.add_argument("--asset", type=Path, required=True)
    verify.add_argument("--distribution-evidence", type=Path, required=True)
    verify.add_argument("--expected-tag")
    verify.add_argument("--expected-git-sha")
    verify.add_argument("--expected-architecture", choices=sorted(EXPECTED_ARCHITECTURES))

    args = parser.parse_args()
    try:
        if args.command == "roundtrip":
            report = build_roundtrip_evidence(
                asset=args.asset,
                distribution_evidence=args.distribution_evidence,
                tag=args.tag,
                architecture=args.architecture,
                expected_git_sha=args.expected_git_sha,
            )
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            report = verify_evidence(
                args.evidence,
                asset=args.asset,
                distribution_evidence=args.distribution_evidence,
                expected_tag=args.expected_tag,
                expected_git_sha=args.expected_git_sha,
                expected_architecture=args.expected_architecture,
            )
    except ValueError as exc:
        raise SystemExit(f"W92 POST-PACKAGE TRUST BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
