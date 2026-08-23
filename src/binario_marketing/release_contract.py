from __future__ import annotations

from typing import Any

SCHEMA = "binario.marketing.source-release-contract.v1"
LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"


def is_development_version(version: str) -> bool:
    value = str(version or "").strip().lower()
    return not value or any(token in value for token in (".dev", "-dev", "alpha", "beta", "rc"))


def evaluate_source_release_contract(
    *,
    version: str,
    release_ready: bool,
    release_tag: str | None,
) -> dict[str, Any]:
    """Classify the immutable source-level release contract without granting release authority.

    LOCKED_SOURCE is the normal development/safety state: no canonical tag is declared.
    PREPARED_RELEASE is a stable source commit prepared *before* physical UAT: the exact
    canonical tag is declared, but the commit still has no operational release authority.
    """
    version = str(version or "").strip()
    if not version:
        raise ValueError("canonical product version is empty")
    development = is_development_version(version)
    expected_tag = f"v{version}"

    if release_ready:
        if development:
            raise ValueError("development/RC source cannot be PREPARED_RELEASE")
        if release_tag != expected_tag:
            raise ValueError(f"prepared release tag mismatch: {release_tag!r} != {expected_tag!r}")
        mode = PREPARED_RELEASE
    else:
        if release_tag is not None:
            raise ValueError("locked source cannot declare RELEASE_TAG")
        mode = LOCKED_SOURCE

    return {
        "schema": SCHEMA,
        "mode": mode,
        "version": version,
        "version_is_development": development,
        "release_ready": bool(release_ready),
        "release_tag": release_tag,
        "expected_tag": expected_tag,
        "source_contract_ready": mode == PREPARED_RELEASE,
        "requires_physical_uat": True,
        "same_commit_must_be_tagged": mode == PREPARED_RELEASE,
        "operational_authorization": False,
        "release_authority": False,
        "production_ready": False,
    }


def validate_source_release_contract(payload: dict[str, Any], *, version: str | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("source release contract must be an object")
    contract_version = str(version if version is not None else payload.get("version") or "").strip()
    expected = evaluate_source_release_contract(
        version=contract_version,
        release_ready=payload.get("release_ready") is True,
        release_tag=payload.get("release_tag"),
    )
    if payload.get("schema") not in {None, SCHEMA}:
        raise ValueError("unexpected source release contract schema")
    if payload.get("mode") not in {None, expected["mode"]}:
        raise ValueError("source release contract mode mismatch")
    for field in ("release_authority", "production_ready", "operational_authorization"):
        if payload.get(field) not in {None, False}:
            raise ValueError(f"source release contract cannot set {field}=true")
    return expected


__all__ = [
    "SCHEMA",
    "LOCKED_SOURCE",
    "PREPARED_RELEASE",
    "is_development_version",
    "evaluate_source_release_contract",
    "validate_source_release_contract",
]
