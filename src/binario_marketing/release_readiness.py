from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .version import RELEASE_READY, RELEASE_TAG, __version__

SCHEMA = "binario.marketing.release-readiness.v1"


@dataclass(frozen=True)
class ReleaseBlocker:
    code: str
    scope: str
    message: str


def _is_development_version(version: str) -> bool:
    value = str(version or "").strip().lower()
    return not value or any(token in value for token in (".dev", "-dev", "alpha", "beta", "rc"))


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


__all__ = ["ReleaseBlocker", "evaluate_release_readiness", "source_release_readiness", "SCHEMA"]
