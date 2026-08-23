from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .version import RELEASE_READY, RELEASE_TAG, __version__

SCHEMA = "binario.marketing.release-readiness.v1"
LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"


@dataclass(frozen=True)
class ReleaseBlocker:
    code: str
    scope: str
    message: str


def _is_development_version(version: str) -> bool:
    value = str(version or "").strip().lower()
    return not value or any(token in value for token in (".dev", "-dev", "alpha", "beta", "rc"))


def source_release_state(
    *,
    version: str = __version__,
    release_ready: bool = RELEASE_READY,
    release_tag: str | None = RELEASE_TAG,
) -> str:
    """Classify the canonical source contract without granting runtime release authority.

    LOCKED_SOURCE is the ordinary fail-closed development/engineering state.
    PREPARED_RELEASE is a stable, tag-bound source state that may be physically UAT-tested
    before the tag exists. It is not distribution trust, production readiness, or authority.
    Any mixed state is rejected instead of being guessed into one of those two states.
    """
    version_value = str(version or "").strip()
    tag_value = str(release_tag or "").strip() or None
    if not release_ready and tag_value is None:
        return LOCKED_SOURCE
    if release_ready is True and not _is_development_version(version_value) and tag_value == f"v{version_value}":
        return PREPARED_RELEASE
    raise ValueError(
        "incoherent canonical release source contract: expected LOCKED_SOURCE "
        "(RELEASE_READY=False, RELEASE_TAG=None) or PREPARED_RELEASE "
        "(stable version, RELEASE_READY=True, RELEASE_TAG=v<version>)"
    )


def evaluate_release_readiness(
    *,
    version: str = __version__,
    release_ready: bool = RELEASE_READY,
    release_tag: str | None = RELEASE_TAG,
    signing_mode: str | None = None,
    notarized: bool | None = None,
    uat_passed: bool | None = None,
    git_sha: str | None = None,
    architecture: str | None = None,
) -> dict[str, Any]:
    blockers: list[ReleaseBlocker] = []
    try:
        source_state = source_release_state(version=version, release_ready=release_ready, release_tag=release_tag)
    except ValueError as exc:
        source_state = "INVALID_SOURCE_CONTRACT"
        blockers.append(ReleaseBlocker("source_release_contract_invalid", "source", str(exc)))

    if _is_development_version(version):
        blockers.append(ReleaseBlocker("development_version", "source", "La versión canónica todavía es de desarrollo/RC."))
    if not release_ready:
        blockers.append(ReleaseBlocker("release_flag_false", "source", "RELEASE_READY permanece en False."))
    if not str(release_tag or "").strip():
        blockers.append(ReleaseBlocker("release_tag_missing", "source", "No existe RELEASE_TAG canónico."))

    if signing_mode is not None and signing_mode != "developer_id":
        blockers.append(ReleaseBlocker("distribution_signing_missing", "distribution", "El bundle no está firmado con Developer ID."))
    if notarized is not None and notarized is not True:
        blockers.append(ReleaseBlocker("notarization_missing", "distribution", "El bundle no está notarizado por Apple."))
    if uat_passed is not None and uat_passed is not True:
        blockers.append(ReleaseBlocker("physical_uat_missing", "uat", "No existe evidencia PASS de UAT física para este candidato."))

    codes = [row.code for row in blockers]
    source_blocked = any(row.scope == "source" for row in blockers)
    distribution_blocked = any(row.scope == "distribution" for row in blockers)
    uat_blocked = any(row.scope == "uat" for row in blockers)
    if source_blocked:
        stage = "DEVELOPMENT"
    elif distribution_blocked or uat_blocked:
        stage = "RELEASE_CANDIDATE_BLOCKED"
    else:
        stage = "PRODUCTION_READY"

    return {
        "schema": SCHEMA,
        "product": "BINARIO Marketing IA",
        "version": version,
        "source_release_state": source_state,
        "release_ready_flag": bool(release_ready),
        "release_tag": release_tag,
        "git_sha": git_sha,
        "architecture": architecture,
        "signing_mode": signing_mode,
        "notarized": notarized,
        "uat_passed": uat_passed,
        "stage": stage,
        "production_ready": not blockers,
        "blocker_codes": codes,
        "blockers": [asdict(row) for row in blockers],
    }


def source_release_readiness() -> dict[str, Any]:
    return evaluate_release_readiness()


__all__ = [
    "ReleaseBlocker",
    "evaluate_release_readiness",
    "source_release_readiness",
    "source_release_state",
    "LOCKED_SOURCE",
    "PREPARED_RELEASE",
    "SCHEMA",
]
