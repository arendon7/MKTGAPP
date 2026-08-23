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
    """Require exact prepared-UAT binding, distribution rebuild trust, and production gating."""
    text = PERSISTENT_RELEASE.read_text(encoding="utf-8") if workflow_text is None else workflow_text
    markers = {
        "PHYSICAL_UAT_ATTESTATION_B64": "persistent release lacks the physical-UAT attestation transport secret",
        "verify_combined_uat_attestation.py": "persistent release lacks combined UAT attestation verification",
        "verify_prepared_release_uat.py": "persistent release lacks same-commit prepared-release physical-UAT verification",
        "prepared-release-uat-verification": "persistent release does not preserve prepared-release UAT verification",
        "verified-physical-uat-attestation": "persistent release lacks a verified UAT attestation artifact",
        "actions/upload-artifact@v4": "persistent release does not upload verified UAT evidence",
        "actions/download-artifact@v4": "persistent release does not download verified UAT evidence for native builds",
        "APPLE_DEVELOPER_ID_P12_BASE64": "persistent release lacks Developer ID certificate transport",
        "APPLE_DEVELOPER_IDENTITY": "persistent release lacks expected Developer ID identity",
        "APPLE_NOTARY_KEY_P8_BASE64": "persistent release lacks App Store Connect notary key transport",
        "build_full_mac_release_candidate.sh --distribution": "persistent release lacks explicit source-equivalent distribution rebuild mode",
        "DISTRIBUTION_REBUILD.json": "persistent release lacks distribution rebuild identity verification",
        "SOURCE_EQUIVALENT_DISTRIBUTION_REBUILD": "persistent release lacks explicit distribution rebuild purpose verification",
        "notarize_release_candidate.sh": "persistent release lacks notarization execution",
        "verify_distribution_trust.py": "persistent release lacks distribution trust verification",
        "release_candidate_gate.py": "persistent release lacks release_candidate_gate.py production enforcement",
        "Package immutable release asset": "persistent release package step is missing",
        "PREPARED-RELEASE-UAT-${{ matrix.arch }}.json": "persistent release package lacks prepared-release UAT verification evidence",
    }
    indexes: dict[str, int] = {}
    for marker, message in markers.items():
        index = text.find(marker)
        if index < 0:
            raise ValueError(message)
        indexes[marker] = index

    uat_verifier = indexes["verify_combined_uat_attestation.py"]
    prepared_verifier = indexes["verify_prepared_release_uat.py"]
    upload = indexes["actions/upload-artifact@v4"]
    download = indexes["actions/download-artifact@v4"]
    rebuild = indexes["build_full_mac_release_candidate.sh --distribution"]
    rebuild_manifest = indexes["DISTRIBUTION_REBUILD.json"]
    notarize = indexes["notarize_release_candidate.sh"]
    dist_verify = indexes["verify_distribution_trust.py"]
    gate = indexes["release_candidate_gate.py"]
    package = indexes["Package immutable release asset"]
    prepared_asset = indexes["PREPARED-RELEASE-UAT-${{ matrix.arch }}.json"]

    if uat_verifier > prepared_verifier:
        raise ValueError("combined UAT attestation must be verified before prepared-release binding")
    if prepared_verifier > upload:
        raise ValueError("prepared-release UAT binding must pass before evidence upload")
    if upload > download:
        raise ValueError("verified UAT evidence must be uploaded before native jobs download it")
    if download > gate:
        raise ValueError("native build must download verified UAT evidence before production gating")
    # W91 intentionally invokes verify_prepared_release_uat.py again in each native job.
    if text.find("verify_prepared_release_uat.py", prepared_verifier + 1) < 0:
        raise ValueError("native release jobs do not re-verify prepared-release UAT binding")
    second_prepared = text.find("verify_prepared_release_uat.py", prepared_verifier + 1)
    if second_prepared < download or second_prepared > rebuild:
        raise ValueError("native prepared-release UAT re-verification must occur after download and before distribution build")
    if rebuild > rebuild_manifest:
        raise ValueError("distribution rebuild must execute before its manifest is verified")
    if rebuild_manifest > notarize:
        raise ValueError("distribution rebuild identity must be verified before notarization")
    if notarize > dist_verify:
        raise ValueError("native distribution must be notarized before distribution evidence verification")
    if dist_verify > gate:
        raise ValueError("distribution trust must be verified before the production release gate")
    if gate > package:
        raise ValueError("production release gate must execute before immutable packaging")
    if prepared_asset < package:
        raise ValueError("prepared-release UAT evidence asset must be emitted only by immutable packaging")

    uat_window = text[uat_verifier:prepared_verifier]
    if "--expected-git-sha" not in uat_window or "GITHUB_SHA" not in uat_window:
        raise ValueError("combined UAT transport is not bound to the exact release commit SHA")
    prepared_window = text[prepared_verifier:upload]
    for marker in ("--expected-git-sha", "--expected-tag", "GITHUB_SHA", "GITHUB_REF_NAME", "combined-physical-uat-attestation.json"):
        if marker not in prepared_window:
            raise ValueError(f"prepared-release UAT preflight missing {marker}")
    native_prepared_window = text[second_prepared:rebuild]
    for marker in ("--expected-git-sha", "--expected-tag", "GITHUB_SHA", "GITHUB_REF_NAME"):
        if marker not in native_prepared_window:
            raise ValueError(f"native prepared-release UAT re-verification missing {marker}")
    rebuild_window = text[rebuild:notarize]
    if "PHYSICAL_UAT_CANDIDATE.json" not in rebuild_window or "test ! -e" not in rebuild_window:
        raise ValueError("distribution rebuild does not prove absence of exact physical-UAT candidate identity")
    if workflow_text is None:
        builder = (ROOT / "scripts" / "build_full_mac_release_candidate.sh").read_text(encoding="utf-8")
        if "--options runtime" not in builder:
            raise ValueError("distribution builder lacks hardened-runtime signing")
    distribution_window = text[notarize:gate]
    for marker in ("--git-sha", "--architecture", "GITHUB_SHA", "matrix.arch"):
        if marker not in distribution_window:
            raise ValueError(f"distribution trust contract missing {marker}")
    gate_window = text[gate:package]
    if "--production" not in gate_window:
        raise ValueError("persistent release gate is not enforcing --production")
    if "--uat-evidence" not in gate_window or "combined-physical-uat-attestation.json" not in gate_window:
        raise ValueError("persistent release gate does not consume verified physical UAT evidence")
    if "--distribution-evidence" not in gate_window or "distribution-trust-${{ matrix.arch }}.json" not in gate_window:
        raise ValueError("persistent release gate does not consume verified distribution trust evidence")
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
