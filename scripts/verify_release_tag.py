#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__  # noqa: E402

TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9.-]+)?$")
PERSISTENT_RELEASE = ROOT / ".github" / "workflows" / "persistent-release.yml"


def verify_pipeline_contract(workflow_text: str | None = None) -> None:
    """Require verified W85 evidence transport and a blocking production gate before packaging."""
    text = PERSISTENT_RELEASE.read_text(encoding="utf-8") if workflow_text is None else workflow_text
    transport_secret = "PHYSICAL_UAT_ATTESTATION_B64"
    verifier_marker = "verify_combined_uat_attestation.py"
    verified_artifact = "verified-physical-uat-attestation"
    upload_marker = "actions/upload-artifact@v4"
    download_marker = "actions/download-artifact@v4"
    gate_marker = "release_candidate_gate.py"
    package_marker = "Package immutable release asset"

    required = {
        transport_secret: "persistent release lacks the physical-UAT attestation transport secret",
        verifier_marker: "persistent release lacks combined UAT attestation verification",
        verified_artifact: "persistent release lacks a verified UAT attestation artifact",
        upload_marker: "persistent release does not upload verified UAT evidence",
        download_marker: "persistent release does not download verified UAT evidence for native builds",
        gate_marker: "persistent release lacks release_candidate_gate.py production enforcement",
        package_marker: "persistent release package step is missing",
    }
    indexes: dict[str, int] = {}
    for marker, message in required.items():
        index = text.find(marker)
        if index < 0:
            raise ValueError(message)
        indexes[marker] = index

    verifier_index = indexes[verifier_marker]
    gate_index = indexes[gate_marker]
    package_index = indexes[package_marker]
    if verifier_index > gate_index:
        raise ValueError("combined UAT attestation must be verified before the production release gate")
    if indexes[upload_marker] > gate_index:
        raise ValueError("verified UAT evidence must be uploaded before native production gating")
    if indexes[download_marker] > gate_index:
        raise ValueError("native build must download verified UAT evidence before production gating")
    if gate_index > package_index:
        raise ValueError("production release gate must execute before immutable packaging")

    verifier_window = text[verifier_index:gate_index]
    if "--expected-git-sha" not in verifier_window or "GITHUB_SHA" not in verifier_window:
        raise ValueError("combined UAT transport is not bound to the exact release commit SHA")
    gate_window = text[gate_index:package_index]
    if "--production" not in gate_window:
        raise ValueError("persistent release gate is not enforcing --production")
    if "--uat-evidence" not in gate_window:
        raise ValueError("persistent release gate does not consume explicit physical UAT evidence")
    if "combined-physical-uat-attestation.json" not in gate_window:
        raise ValueError("persistent release gate is not consuming the verified combined attestation")
    if "--expect-blocked" in gate_window:
        raise ValueError("persistent release cannot substitute --expect-blocked for production enforcement")
    if "|| true" in gate_window:
        raise ValueError("persistent release production gate cannot be made non-blocking")


def verify(tag: str) -> None:
    if not TAG_RE.fullmatch(tag):
        raise ValueError(f"invalid release tag format: {tag}")
    if not RELEASE_READY:
        raise ValueError("release publishing is disabled by the canonical version contract")
    if not RELEASE_TAG:
        raise ValueError("release publishing is enabled but RELEASE_TAG is unset")
    expected = f"v{__version__}"
    if RELEASE_TAG != expected:
        raise ValueError(f"canonical RELEASE_TAG drift: {RELEASE_TAG} != {expected}")
    if tag != RELEASE_TAG:
        raise ValueError(f"tag mismatch: {tag} != {RELEASE_TAG}")
    verify_pipeline_contract()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    try:
        verify(args.tag)
    except (OSError, ValueError) as exc:
        print(f"RELEASE TAG BLOCKED: {exc}", file=sys.stderr)
        return 4
    print(f"RELEASE TAG PASS: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
