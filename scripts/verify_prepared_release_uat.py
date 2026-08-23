#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import runpy
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from binario_marketing.release_contract import PREPARED_RELEASE, evaluate_source_release_contract  # noqa: E402
from verify_combined_uat_attestation import verify as verify_combined_uat  # noqa: E402

SCHEMA = "binario.marketing.prepared-release-uat-verification.v1"
CONTRACT_WAVE = 91


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _source_digest(repo: Path) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for root in (repo / "src", repo / "web", repo / "apps"):
        _require(root.is_dir(), f"source root missing: {root}")
        files.extend(path for path in root.rglob("*") if path.is_file())
    for path in sorted(files, key=lambda item: item.relative_to(repo).as_posix()):
        relative = path.relative_to(repo).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _source_contract(repo: Path) -> dict[str, Any]:
    version_path = repo / "src/binario_marketing/version.py"
    _require(version_path.is_file(), "canonical version.py missing")
    values = runpy.run_path(str(version_path))
    return evaluate_source_release_contract(
        version=str(values.get("__version__") or ""),
        release_ready=values.get("RELEASE_READY") is True,
        release_tag=values.get("RELEASE_TAG"),
    )


def verify(
    repo: Path,
    evidence: Path,
    *,
    expected_git_sha: str,
    expected_tag: str,
) -> dict[str, Any]:
    repo = repo.expanduser().resolve()
    evidence = evidence.expanduser().resolve()
    _require(repo.is_dir(), f"repository root missing: {repo}")
    _require(len(str(expected_git_sha or "")) == 40, "expected release git SHA must be a full 40-character SHA")
    _require(str(expected_tag or "").startswith("v"), "expected release tag must start with v")

    source_contract = _source_contract(repo)
    _require(source_contract.get("mode") == PREPARED_RELEASE, "canonical source is not PREPARED_RELEASE")
    _require(source_contract.get("release_authority") is False, "source contract unexpectedly carries release authority")
    _require(source_contract.get("production_ready") is False, "source contract unexpectedly claims production readiness")
    _require(source_contract.get("release_tag") == expected_tag, "canonical prepared release tag does not match workflow tag")
    _require(source_contract.get("expected_tag") == expected_tag, "prepared release expected tag drift")

    combined = verify_combined_uat(evidence, expected_git_sha=expected_git_sha)
    attested_contract = combined.get("source_release_contract")
    _require(isinstance(attested_contract, dict), "combined UAT lacks W91 source release contract binding")
    _require(attested_contract.get("mode") == PREPARED_RELEASE, "physical UAT was not performed on PREPARED_RELEASE source")
    for field in ("version", "release_ready", "release_tag"):
        _require(attested_contract.get(field) == source_contract.get(field), f"prepared release UAT/source contract mismatch: {field}")
    _require(attested_contract.get("release_tag") == expected_tag, "physical UAT prepared tag does not match workflow tag")
    _require(combined.get("product_version") == source_contract.get("version"), "physical UAT product version differs from canonical source")
    _require(combined.get("prepared_release_contract_wave") == CONTRACT_WAVE, "combined UAT lacks W91 prepared-release contract layer")

    current_source_sha = _source_digest(repo)
    _require(combined.get("candidate_source_sha256") == current_source_sha, "physical UAT source digest differs from tag checkout")

    return {
        "schema": SCHEMA,
        "contract_wave": CONTRACT_WAVE,
        "git_sha": expected_git_sha,
        "tag": expected_tag,
        "version": source_contract.get("version"),
        "source_sha256": current_source_sha,
        "source_release_contract": source_contract,
        "physical_uat_attestation_sha256": combined.get("attestation_sha256"),
        "candidate_manifest_sha256": combined.get("candidate_manifest_sha256"),
        "same_commit_physically_tested": True,
        "same_source_digest_physically_tested": True,
        "prepared_before_physical_uat": True,
        "operational_authorization": False,
        "release_authority": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that a release tag points to the exact prepared source commit physically tested on main.")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--expected-git-sha", required=True)
    parser.add_argument("--expected-tag", required=True)
    args = parser.parse_args()
    try:
        report = verify(
            args.repo,
            args.evidence,
            expected_git_sha=args.expected_git_sha,
            expected_tag=args.expected_tag,
        )
    except ValueError as exc:
        raise SystemExit(f"PREPARED RELEASE UAT BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
