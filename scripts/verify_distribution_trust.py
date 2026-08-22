#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.distribution-trust.v1"


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid distribution trust evidence: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("distribution trust evidence must be a JSON object")
    return data


def _digest(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def verify(path: Path, *, git_sha: str | None = None, architecture: str | None = None, product_version: str | None = None) -> dict[str, Any]:
    path = path.expanduser().resolve()
    _require(path.is_file(), f"distribution trust evidence missing: {path}")
    data = _load(path)
    _require(data.get("schema") == SCHEMA, "unexpected distribution trust schema")
    evidence_sha = str(data.get("evidence_sha256") or "")
    _require(len(evidence_sha) == 64, "distribution trust digest missing or malformed")
    core = dict(data)
    core.pop("evidence_sha256", None)
    _require(_digest(core) == evidence_sha, "distribution trust digest mismatch")
    evidence_git_sha = str(data.get("git_sha") or "")
    _require(len(evidence_git_sha) == 40, "distribution trust git SHA missing or malformed")
    if git_sha is not None:
        _require(evidence_git_sha == git_sha, f"distribution trust git SHA mismatch: {evidence_git_sha} != {git_sha}")
    if architecture is not None:
        _require(data.get("architecture") == architecture, "distribution trust architecture mismatch")
    if product_version is not None:
        _require(data.get("product_version") == product_version, "distribution trust version mismatch")
    _require(data.get("runtime_wave") == 76, "distribution trust runtime wave drift")
    _require(data.get("signing_mode") == "developer_id", "Developer ID signing is not verified")
    _require(str(data.get("developer_id_identity") or "").startswith("Developer ID Application:"), "Developer ID identity missing")
    _require(data.get("notarized") is True, "notarization is not verified")
    _require(str(data.get("notary_status") or "").lower() == "accepted", "notary status is not Accepted")
    _require(bool(str(data.get("notary_submission_id") or "").strip()), "notary submission id missing")
    _require(data.get("stapler_validated") is True, "stapled ticket is not verified")
    _require(data.get("gatekeeper_assessed") is True, "Gatekeeper assessment is not verified")
    _require(data.get("release_authority") is False, "distribution evidence must not carry release authority")
    return {
        "schema": SCHEMA,
        "git_sha": evidence_git_sha,
        "architecture": data.get("architecture"),
        "product_version": data.get("product_version"),
        "runtime_wave": 76,
        "signing_mode": "developer_id",
        "notarized": True,
        "notary_submission_id": data.get("notary_submission_id"),
        "evidence_sha256": evidence_sha,
        "release_authority": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Developer ID + notarization evidence for one native BINARIO distribution asset.")
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--git-sha")
    parser.add_argument("--architecture")
    parser.add_argument("--product-version")
    args = parser.parse_args()
    try:
        report = verify(args.evidence, git_sha=args.git_sha, architecture=args.architecture, product_version=args.product_version)
    except ValueError as exc:
        raise SystemExit(f"DISTRIBUTION TRUST BLOCKED: {exc}") from exc
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
