#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.release-artifact-authorization.v1"
RUNTIME_WAVE = 76
CERTIFICATION_GUARD_WAVE = 92


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid authorization JSON: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"authorization JSON must be an object: {path}")
    return data


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _seal(payload: dict[str, Any]) -> dict[str, Any]:
    core = dict(payload)
    core.pop("authorization_sha256", None)
    result = dict(core)
    result["authorization_sha256"] = _digest(core)
    return result


def _verify_seal(payload: dict[str, Any]) -> None:
    expected = str(payload.get("authorization_sha256") or "")
    _require(len(expected) == 64, "W92 authorization digest missing or malformed")
    core = dict(payload)
    core.pop("authorization_sha256", None)
    _require(_digest(core) == expected, "W92 authorization digest mismatch")


def _scripts_path() -> Path:
    return Path(__file__).resolve().parent


def _load_verified_inputs(
    *,
    w91_authorization: Path,
    arm64_evidence: Path,
    x86_evidence: Path,
    asset_dir: Path,
    arm64_release_manifest: Path,
    x86_release_manifest: Path,
    arm64_post_package: Path,
    x86_post_package: Path,
    arm64_distribution_evidence: Path,
    x86_distribution_evidence: Path,
    expected_tag: str | None,
    expected_git_sha: str | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    scripts = _scripts_path()
    sys.path.insert(0, str(scripts))
    try:
        from release_evidence_chain import verify_release_authorization
        from verify_packaged_release_asset import verify_evidence as verify_post_package
        w91 = verify_release_authorization(
            w91_authorization,
            arm64_evidence=arm64_evidence,
            x86_evidence=x86_evidence,
            asset_dir=asset_dir,
            arm64_release_manifest=arm64_release_manifest,
            x86_release_manifest=x86_release_manifest,
            expected_tag=expected_tag,
            expected_git_sha=expected_git_sha,
        )
        arm_native = _load(arm64_evidence)
        x86_native = _load(x86_evidence)
        arm_asset = asset_dir / str((arm_native.get("asset") or {}).get("name") or "")
        x86_asset = asset_dir / str((x86_native.get("asset") or {}).get("name") or "")
        arm_post = verify_post_package(
            arm64_post_package,
            asset=arm_asset,
            distribution_evidence=arm64_distribution_evidence,
            expected_tag=expected_tag,
            expected_git_sha=expected_git_sha,
            expected_architecture="arm64",
        )
        x86_post = verify_post_package(
            x86_post_package,
            asset=x86_asset,
            distribution_evidence=x86_distribution_evidence,
            expected_tag=expected_tag,
            expected_git_sha=expected_git_sha,
            expected_architecture="x86_64",
        )
    finally:
        try:
            sys.path.remove(str(scripts))
        except ValueError:
            pass
    return w91, arm_native, x86_native, arm_post, x86_post


def _bind_native_chain(native: dict[str, Any], post: dict[str, Any], *, architecture: str) -> dict[str, Any]:
    _require(native.get("architecture") == architecture, f"{architecture} native evidence architecture mismatch")
    _require(post.get("architecture") == architecture, f"{architecture} post-package architecture mismatch")
    for key in ("tag", "git_sha", "product_version", "runtime_wave", "source_sha256"):
        _require(native.get(key) == post.get(key), f"{architecture} native/post-package {key} mismatch")
    native_asset = native.get("asset") or {}
    post_asset = post.get("asset") or {}
    _require(native_asset.get("name") == post_asset.get("name"), f"{architecture} native/post-package asset name mismatch")
    _require(native_asset.get("sha256") == post_asset.get("sha256"), f"{architecture} native/post-package asset digest mismatch")
    _require(native_asset.get("size_bytes") == post_asset.get("size_bytes"), f"{architecture} native/post-package asset size mismatch")

    native_trust = native.get("distribution_trust") or {}
    post_trust = post.get("pre_package_distribution_trust") or {}
    _require(native_trust.get("evidence_file_sha256") == post_trust.get("evidence_file_sha256"), f"{architecture} distribution evidence file mismatch")
    _require(native_trust.get("evidence_sha256") == post_trust.get("evidence_sha256"), f"{architecture} distribution trust digest mismatch")
    _require(native_trust.get("notary_submission_id") == post_trust.get("notary_submission_id"), f"{architecture} notary submission mismatch")

    native_rebuild = native.get("distribution_rebuild") or {}
    extracted = post.get("extracted_app") or {}
    _require(native_rebuild.get("manifest_sha256") == extracted.get("distribution_rebuild_manifest_sha256"), f"{architecture} extracted rebuild manifest mismatch")
    native_inputs = native.get("build_inputs") or {}
    _require(native_inputs.get("build_provenance_sha256") == extracted.get("build_provenance_sha256"), f"{architecture} extracted build provenance mismatch")
    _require(post.get("asset_roundtrip_verified") is True, f"{architecture} asset round-trip verification missing")
    trust = post.get("roundtrip_trust") or {}
    for key in ("codesign_verified", "stapler_validated", "gatekeeper_assessed"):
        _require(trust.get(key) is True, f"{architecture} round-trip trust gate missing: {key}")

    return {
        "asset": native_asset.get("name"),
        "asset_sha256": native_asset.get("sha256"),
        "release_evidence_sha256": native.get("evidence_sha256"),
        "post_package_evidence_sha256": post.get("evidence_sha256"),
        "developer_id_identity": trust.get("developer_id_identity"),
        "notary_submission_id": post_trust.get("notary_submission_id"),
        "codesign_verified_after_roundtrip": True,
        "stapler_validated_after_roundtrip": True,
        "gatekeeper_assessed_after_roundtrip": True,
    }


def build_authorization(
    *,
    w91: dict[str, Any],
    arm_native: dict[str, Any],
    x86_native: dict[str, Any],
    arm_post: dict[str, Any],
    x86_post: dict[str, Any],
) -> dict[str, Any]:
    _require(w91.get("release_authority") is True, "W91 release authority missing")
    _require(w91.get("operational_authorization") is True, "W91 operational authorization missing")
    _require(w91.get("production_ready") is True, "W91 authorization is not production ready")
    _require(w91.get("publication_performed") is False, "W91 authorization must precede publication")

    arm = _bind_native_chain(arm_native, arm_post, architecture="arm64")
    x86 = _bind_native_chain(x86_native, x86_post, architecture="x86_64")
    for key in ("tag", "git_sha", "product_version", "runtime_wave", "source_sha256"):
        _require(arm_native.get(key) == x86_native.get(key), f"cross-architecture {key} mismatch")

    payload = {
        "schema": SCHEMA,
        "tag": arm_native["tag"],
        "git_sha": arm_native["git_sha"],
        "product_version": arm_native["product_version"],
        "runtime_wave": RUNTIME_WAVE,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "source_sha256": arm_native["source_sha256"],
        "w91_release_authorization_sha256": w91.get("authorization_sha256"),
        "native_assets": {
            "arm64": arm,
            "x86_64": x86,
        },
        "roundtrip_publication_gates": {
            "w91_release_authorization_verified": True,
            "both_native_assets_hash_bound": True,
            "both_archives_path_safe": True,
            "both_extracted_apps_match_native_evidence": True,
            "both_developer_id_signatures_survive_roundtrip": True,
            "both_notarization_tickets_survive_roundtrip": True,
            "both_gatekeeper_assessments_pass_after_roundtrip": True,
        },
        "operational_authorization": True,
        "release_authority": True,
        "publication_authority": True,
        "production_ready": True,
        "publication_performed": False,
        "mutations_performed": False,
    }
    return _seal(payload)


def verify_authorization(
    authorization_path: Path,
    **kwargs: Any,
) -> dict[str, Any]:
    w91, arm_native, x86_native, arm_post, x86_post = _load_verified_inputs(**kwargs)
    expected = build_authorization(
        w91=w91,
        arm_native=arm_native,
        x86_native=x86_native,
        arm_post=arm_post,
        x86_post=x86_post,
    )
    actual = _load(authorization_path.expanduser().resolve())
    _require(actual == expected, "W92 artifact publication authorization drift")
    _verify_seal(actual)
    _require(actual.get("publication_authority") is True, "W92 publication authority missing")
    _require(actual.get("production_ready") is True, "W92 authorization is not production ready")
    _require(actual.get("publication_performed") is False, "W92 authorization must precede publication")
    _require(actual.get("mutations_performed") is False, "W92 authorization generation must not publish")
    return actual


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--w91-authorization", type=Path, required=True)
    parser.add_argument("--arm64-evidence", type=Path, required=True)
    parser.add_argument("--x86-evidence", type=Path, required=True)
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--arm64-release-manifest", type=Path, required=True)
    parser.add_argument("--x86-release-manifest", type=Path, required=True)
    parser.add_argument("--arm64-post-package", type=Path, required=True)
    parser.add_argument("--x86-post-package", type=Path, required=True)
    parser.add_argument("--arm64-distribution-evidence", type=Path, required=True)
    parser.add_argument("--x86-distribution-evidence", type=Path, required=True)
    parser.add_argument("--expected-tag")
    parser.add_argument("--expected-git-sha")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the final W92 publication authorization only after W91 plus both packaged ZIP round-trip trust gates pass.")
    sub = parser.add_subparsers(dest="command", required=True)
    authorize = sub.add_parser("authorize")
    _add_common(authorize)
    authorize.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify-authorization")
    _add_common(verify)
    verify.add_argument("--authorization", type=Path, required=True)
    args = parser.parse_args()

    kwargs = {
        "w91_authorization": args.w91_authorization,
        "arm64_evidence": args.arm64_evidence,
        "x86_evidence": args.x86_evidence,
        "asset_dir": args.asset_dir,
        "arm64_release_manifest": args.arm64_release_manifest,
        "x86_release_manifest": args.x86_release_manifest,
        "arm64_post_package": args.arm64_post_package,
        "x86_post_package": args.x86_post_package,
        "arm64_distribution_evidence": args.arm64_distribution_evidence,
        "x86_distribution_evidence": args.x86_distribution_evidence,
        "expected_tag": args.expected_tag,
        "expected_git_sha": args.expected_git_sha,
    }
    try:
        if args.command == "authorize":
            w91, arm_native, x86_native, arm_post, x86_post = _load_verified_inputs(**kwargs)
            report = build_authorization(
                w91=w91,
                arm_native=arm_native,
                x86_native=x86_native,
                arm_post=arm_post,
                x86_post=x86_post,
            )
            output = args.output.expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        else:
            report = verify_authorization(args.authorization, **kwargs)
    except ValueError as exc:
        raise SystemExit(f"W92 ARTIFACT AUTHORIZATION BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
