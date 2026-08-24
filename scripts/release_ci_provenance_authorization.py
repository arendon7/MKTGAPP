#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.release-ci-provenance-authorization.v2"
RUNTIME_WAVE = 76
CERTIFICATION_GUARD_WAVE = 94
PREDICATE_TYPE = "https://slsa.dev/provenance/v1"
GITHUB_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
EXPECTED_WORKFLOW_PATH = ".github/workflows/persistent-release.yml"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc


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
    core.pop("authorization_sha256", None)
    result = dict(core)
    result["authorization_sha256"] = _digest(core)
    return result


def _verify_seal(payload: dict[str, Any]) -> None:
    expected = str(payload.get("authorization_sha256") or "")
    _require(len(expected) == 64, "W94 authorization digest missing or malformed")
    core = dict(payload)
    core.pop("authorization_sha256", None)
    _require(_digest(core) == expected, "W94 authorization digest mismatch")


def _validate_identity(*, repository: str, signer_workflow: str, source_ref: str, source_digest: str) -> None:
    _require(repository.count("/") == 1 and not repository.startswith("/") and not repository.endswith("/"), "repository must be owner/name")
    _require(signer_workflow == f"{repository}/{EXPECTED_WORKFLOW_PATH}", f"unexpected signer workflow: {signer_workflow}")
    _require(source_ref.startswith("refs/tags/v"), "W94 source ref must be a canonical release tag ref")
    _require(len(source_digest) == 40 and all(ch in "0123456789abcdef" for ch in source_digest.lower()), "source digest must be a 40-character git SHA")


def _verification_command(
    *,
    asset: Path,
    bundle: Path,
    repository: str,
    signer_workflow: str,
    source_ref: str,
    source_digest: str,
) -> list[str]:
    _validate_identity(repository=repository, signer_workflow=signer_workflow, source_ref=source_ref, source_digest=source_digest)
    return [
        "gh", "attestation", "verify", str(asset),
        "--bundle", str(bundle),
        "--repo", repository,
        "--signer-workflow", signer_workflow,
        "--source-ref", source_ref,
        "--source-digest", source_digest,
        "--cert-oidc-issuer", GITHUB_OIDC_ISSUER,
        "--deny-self-hosted-runners",
        "--predicate-type", PREDICATE_TYPE,
        "--format", "json",
    ]


def _run_verification(command: list[str]) -> Any:
    try:
        result = subprocess.run(command, check=True, text=True, capture_output=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (exc.stderr or exc.stdout or "").strip() if isinstance(exc, subprocess.CalledProcessError) else str(exc)
        raise ValueError(f"GitHub attestation verification failed: {detail}") from exc
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("GitHub attestation verification did not return valid JSON") from exc


def _subject_matches_name(name: str, asset_name: str) -> bool:
    normalized = str(name or "").replace("\\", "/").rstrip("/")
    return normalized == asset_name or normalized.endswith(f"/{asset_name}")


def _validate_verification_output(output: Any, *, asset: Path) -> dict[str, Any]:
    _require(isinstance(output, list) and bool(output), "no verified GitHub attestations returned")
    asset_sha = _sha256_file(asset)
    matching = 0
    timestamps = 0
    for row in output:
        _require(isinstance(row, dict), "verified attestation result must be an object")
        verification = row.get("verificationResult")
        _require(isinstance(verification, dict), "verificationResult missing from GitHub attestation output")
        statement = verification.get("statement")
        _require(isinstance(statement, dict), "verified in-toto statement missing")
        _require(statement.get("predicateType") == PREDICATE_TYPE, "verified attestation predicate type mismatch")
        subjects = statement.get("subject")
        _require(isinstance(subjects, list) and bool(subjects), "verified attestation subject list missing")
        for subject in subjects:
            if not isinstance(subject, dict):
                continue
            digest = subject.get("digest")
            if not isinstance(digest, dict):
                continue
            if _subject_matches_name(str(subject.get("name") or ""), asset.name) and str(digest.get("sha256") or "").lower() == asset_sha:
                matching += 1
        verified_timestamps = verification.get("verifiedTimestamps")
        if isinstance(verified_timestamps, list):
            timestamps += len(verified_timestamps)
    _require(matching > 0, "verified attestation does not bind the exact asset name and SHA-256")
    _require(timestamps > 0, "verified attestation has no transparency/timestamp witness")
    return {
        "verified_attestation_count": len(output),
        "matching_subject_count": matching,
        "verified_timestamp_count": timestamps,
        "subject_name": asset.name,
        "subject_sha256": asset_sha,
    }


def verify_ci_provenance(
    *, asset: Path, bundle: Path, repository: str, signer_workflow: str, source_ref: str, source_digest: str,
) -> dict[str, Any]:
    asset = asset.expanduser().resolve()
    bundle = bundle.expanduser().resolve()
    _require(asset.is_file(), f"release asset missing: {asset}")
    _require(bundle.is_file(), f"Sigstore provenance bundle missing: {bundle}")
    output = _run_verification(_verification_command(
        asset=asset, bundle=bundle, repository=repository, signer_workflow=signer_workflow,
        source_ref=source_ref, source_digest=source_digest,
    ))
    validated = _validate_verification_output(output, asset=asset)
    return {
        "asset": asset.name,
        "asset_sha256": validated["subject_sha256"],
        "bundle_sha256": _sha256_file(bundle),
        "repository": repository,
        "signer_workflow": signer_workflow,
        "source_ref": source_ref,
        "source_digest": source_digest,
        "predicate_type": PREDICATE_TYPE,
        "oidc_issuer": GITHUB_OIDC_ISSUER,
        "deny_self_hosted_runners": True,
        "verified_attestation_count": validated["verified_attestation_count"],
        "matching_subject_count": validated["matching_subject_count"],
        "verified_timestamp_count": validated["verified_timestamp_count"],
        "cryptographic_attestation_verified": True,
    }


def _scripts_path() -> Path:
    return Path(__file__).resolve().parent


def _verify_w92_authorization(
    *, w92_authorization: Path, w91_authorization: Path, arm64_evidence: Path, x86_evidence: Path,
    asset_dir: Path, arm64_release_manifest: Path, x86_release_manifest: Path,
    arm64_post_package: Path, x86_post_package: Path, arm64_distribution_evidence: Path,
    x86_distribution_evidence: Path, expected_tag: str, expected_git_sha: str,
) -> dict[str, Any]:
    scripts = _scripts_path()
    sys.path.insert(0, str(scripts))
    try:
        from release_artifact_authorization import verify_authorization
        return verify_authorization(
            w92_authorization,
            w91_authorization=w91_authorization,
            arm64_evidence=arm64_evidence,
            x86_evidence=x86_evidence,
            asset_dir=asset_dir,
            arm64_release_manifest=arm64_release_manifest,
            x86_release_manifest=x86_release_manifest,
            arm64_post_package=arm64_post_package,
            x86_post_package=x86_post_package,
            arm64_distribution_evidence=arm64_distribution_evidence,
            x86_distribution_evidence=x86_distribution_evidence,
            expected_tag=expected_tag,
            expected_git_sha=expected_git_sha,
        )
    finally:
        try:
            sys.path.remove(str(scripts))
        except ValueError:
            pass


def _asset_path(w92: dict[str, Any], asset_dir: Path, architecture: str) -> Path:
    native = (w92.get("native_assets") or {}).get(architecture)
    _require(isinstance(native, dict), f"W92 {architecture} native asset authorization missing")
    name = str(native.get("asset") or "")
    expected_sha = str(native.get("asset_sha256") or "")
    _require(bool(name) and len(expected_sha) == 64, f"W92 {architecture} asset identity missing")
    asset = asset_dir / name
    _require(asset.is_file(), f"W92 {architecture} release asset missing: {asset}")
    _require(_sha256_file(asset) == expected_sha, f"W92 {architecture} release asset digest mismatch")
    return asset


def _validate_provenance(
    *, architecture: str, provenance: dict[str, Any], w92: dict[str, Any], repository: str,
    signer_workflow: str, source_ref: str, source_digest: str,
) -> None:
    _require(provenance.get("cryptographic_attestation_verified") is True, f"{architecture} GitHub provenance is not verified")
    _require(provenance.get("repository") == repository, f"{architecture} provenance repository mismatch")
    _require(provenance.get("signer_workflow") == signer_workflow, f"{architecture} provenance signer workflow mismatch")
    _require(provenance.get("source_ref") == source_ref, f"{architecture} provenance source ref mismatch")
    _require(provenance.get("source_digest") == source_digest, f"{architecture} provenance source digest mismatch")
    _require(provenance.get("predicate_type") == PREDICATE_TYPE, f"{architecture} provenance predicate type mismatch")
    _require(provenance.get("oidc_issuer") == GITHUB_OIDC_ISSUER, f"{architecture} provenance OIDC issuer mismatch")
    _require(provenance.get("deny_self_hosted_runners") is True, f"{architecture} provenance does not deny self-hosted runners")
    native = (w92.get("native_assets") or {}).get(architecture) or {}
    _require(provenance.get("asset") == native.get("asset"), f"{architecture} W92/provenance asset mismatch")
    _require(provenance.get("asset_sha256") == native.get("asset_sha256"), f"{architecture} W92/provenance asset digest mismatch")


def build_authorization(
    *, w92: dict[str, Any], arm64_provenance: dict[str, Any], x86_provenance: dict[str, Any],
    repository: str, signer_workflow: str, source_ref: str, source_digest: str,
    transaction_script_sha256: str,
) -> dict[str, Any]:
    _require(w92.get("schema") == "binario.marketing.release-artifact-authorization.v1", "unexpected W92 authorization schema")
    _require(w92.get("publication_authority") is True, "W92 publication authority missing")
    _require(w92.get("production_ready") is True, "W92 authorization is not production ready")
    _require(w92.get("publication_performed") is False, "W92 authorization must precede publication")
    _require(w92.get("mutations_performed") is False, "W92 authorization must be mutation-free")
    _require(w92.get("git_sha") == source_digest, "W92/source digest mismatch")
    _require(f"refs/tags/{w92.get('tag')}" == source_ref, "W92/source ref mismatch")
    _require(len(transaction_script_sha256) == 64, "transaction script digest missing or malformed")
    _validate_identity(repository=repository, signer_workflow=signer_workflow, source_ref=source_ref, source_digest=source_digest)
    _validate_provenance(architecture="arm64", provenance=arm64_provenance, w92=w92, repository=repository, signer_workflow=signer_workflow, source_ref=source_ref, source_digest=source_digest)
    _validate_provenance(architecture="x86_64", provenance=x86_provenance, w92=w92, repository=repository, signer_workflow=signer_workflow, source_ref=source_ref, source_digest=source_digest)

    payload = {
        "schema": SCHEMA,
        "tag": w92.get("tag"),
        "git_sha": w92.get("git_sha"),
        "product_version": w92.get("product_version"),
        "runtime_wave": RUNTIME_WAVE,
        "certification_guard_wave": CERTIFICATION_GUARD_WAVE,
        "source_sha256": w92.get("source_sha256"),
        "w92_artifact_authorization_sha256": w92.get("authorization_sha256"),
        "transaction": {
            "script": "scripts/publish_release_transaction.sh",
            "script_sha256": transaction_script_sha256,
            "github_release_roundtrip_required": True,
        },
        "ci_identity": {
            "repository": repository,
            "signer_workflow": signer_workflow,
            "source_ref": source_ref,
            "source_digest": source_digest,
            "oidc_issuer": GITHUB_OIDC_ISSUER,
            "predicate_type": PREDICATE_TYPE,
            "self_hosted_runners_denied": True,
        },
        "native_provenance": {"arm64": arm64_provenance, "x86_64": x86_provenance},
        "provenance_handoff_gates": {
            "w92_artifact_authorization_verified": True,
            "arm64_github_oidc_provenance_verified": True,
            "x86_64_github_oidc_provenance_verified": True,
            "same_repository_and_signer_workflow": True,
            "same_tag_ref_and_source_commit": True,
            "exact_native_asset_digests_attested": True,
            "transaction_script_hash_bound": True,
            "self_hosted_runners_denied": True,
        },
        "operational_authorization": True,
        "release_authority": True,
        "transaction_handoff_authority": True,
        "publication_authority": False,
        "production_ready": True,
        "publication_performed": False,
        "mutations_performed": False,
    }
    return _seal(payload)


def verify_transaction_handoff(
    authorization_path: Path, *, transaction_script: Path, expected_tag: str, expected_git_sha: str,
) -> dict[str, Any]:
    actual = _load_json(authorization_path.expanduser().resolve())
    _require(isinstance(actual, dict), "W94 authorization must be a JSON object")
    _require(actual.get("schema") == SCHEMA, "unexpected W94 authorization schema")
    _verify_seal(actual)
    _require(actual.get("tag") == expected_tag, "W94 handoff tag mismatch")
    _require(actual.get("git_sha") == expected_git_sha, "W94 handoff git SHA mismatch")
    transaction = actual.get("transaction") or {}
    _require(transaction.get("script") == "scripts/publish_release_transaction.sh", "W94 transaction script path mismatch")
    _require(transaction.get("script_sha256") == _sha256_file(transaction_script.expanduser().resolve()), "W94 transaction script digest mismatch")
    _require(actual.get("transaction_handoff_authority") is True, "W94 transaction handoff authority missing")
    _require(actual.get("publication_authority") is False, "W94 must not self-grant publication authority")
    _require(actual.get("production_ready") is True, "W94 handoff is not production ready")
    _require(actual.get("publication_performed") is False, "W94 handoff must precede publication")
    _require(actual.get("mutations_performed") is False, "W94 handoff must be mutation-free")
    return actual


def _common_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "w92_authorization": args.w92_authorization,
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


def _compute(args: argparse.Namespace) -> dict[str, Any]:
    _require(args.expected_tag == args.source_ref.removeprefix("refs/tags/"), "expected tag/source ref mismatch")
    _require(args.expected_git_sha == args.source_digest, "expected git SHA/source digest mismatch")
    w92 = _verify_w92_authorization(**_common_kwargs(args))
    arm_asset = _asset_path(w92, args.asset_dir, "arm64")
    x86_asset = _asset_path(w92, args.asset_dir, "x86_64")
    arm = verify_ci_provenance(asset=arm_asset, bundle=args.arm64_bundle, repository=args.repository, signer_workflow=args.signer_workflow, source_ref=args.source_ref, source_digest=args.source_digest)
    x86 = verify_ci_provenance(asset=x86_asset, bundle=args.x86_bundle, repository=args.repository, signer_workflow=args.signer_workflow, source_ref=args.source_ref, source_digest=args.source_digest)
    return build_authorization(
        w92=w92,
        arm64_provenance=arm,
        x86_provenance=x86,
        repository=args.repository,
        signer_workflow=args.signer_workflow,
        source_ref=args.source_ref,
        source_digest=args.source_digest,
        transaction_script_sha256=_sha256_file(args.transaction_script.expanduser().resolve()),
    )


def _add_full_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--w92-authorization", type=Path, required=True)
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
    parser.add_argument("--arm64-bundle", type=Path, required=True)
    parser.add_argument("--x86-bundle", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--signer-workflow", required=True)
    parser.add_argument("--source-ref", required=True)
    parser.add_argument("--source-digest", required=True)
    parser.add_argument("--transaction-script", type=Path, required=True)
    parser.add_argument("--expected-tag", required=True)
    parser.add_argument("--expected-git-sha", required=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify W94 GitHub OIDC/Sigstore provenance handoff into the transactional W93 publication boundary.")
    sub = parser.add_subparsers(dest="command", required=True)
    authorize = sub.add_parser("authorize")
    _add_full_args(authorize)
    authorize.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("verify-authorization")
    _add_full_args(verify)
    verify.add_argument("--authorization", type=Path, required=True)
    handoff = sub.add_parser("verify-transaction-handoff")
    handoff.add_argument("--authorization", type=Path, required=True)
    handoff.add_argument("--transaction-script", type=Path, required=True)
    handoff.add_argument("--expected-tag", required=True)
    handoff.add_argument("--expected-git-sha", required=True)
    args = parser.parse_args()
    try:
        if args.command == "verify-transaction-handoff":
            report = verify_transaction_handoff(
                args.authorization,
                transaction_script=args.transaction_script,
                expected_tag=args.expected_tag,
                expected_git_sha=args.expected_git_sha,
            )
        else:
            expected = _compute(args)
            if args.command == "authorize":
                output = args.output.expanduser().resolve()
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_text(json.dumps(expected, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
                report = expected
            else:
                actual = _load_json(args.authorization.expanduser().resolve())
                _require(isinstance(actual, dict), "W94 authorization must be a JSON object")
                _require(actual == expected, "W94 CI provenance authorization drift")
                _verify_seal(actual)
                _require(actual.get("transaction_handoff_authority") is True, "W94 transaction handoff authority missing")
                _require(actual.get("publication_authority") is False, "W94 must not self-grant publication authority")
                _require(actual.get("production_ready") is True, "W94 authorization is not production ready")
                _require(actual.get("publication_performed") is False, "W94 authorization must precede publication")
                _require(actual.get("mutations_performed") is False, "W94 authorization generation must not publish")
                report = actual
    except ValueError as exc:
        raise SystemExit(f"W94 CI PROVENANCE AUTHORIZATION BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
