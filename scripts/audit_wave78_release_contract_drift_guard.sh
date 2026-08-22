#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave78_release_contract_drift_guard.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
W69="$SRC/src/binario_marketing/service_wave69_app.py"
W71="$SRC/src/binario_marketing/service_wave71_app.py"
W75="$SRC/src/binario_marketing/service_wave75_app.py"
W76="$SRC/src/binario_marketing/service_wave76_app.py"

[[ -f "$W69" && -f "$W71" && -f "$W75" && -f "$W76" ]]
[[ -f "$LAUNCH" && -x "$PYTHON" ]]
/usr/bin/grep -q 'ready_to_begin_physical_uat' "$W69"
/usr/bin/grep -q 'preflight.get("ready_to_begin_physical_uat")' "$W71"
! /usr/bin/grep -q 'preflight.get("ready_for_physical_uat")' "$W71"
/usr/bin/grep -q 'synthetic UAT sandbox is functional-only and cannot record physical release evidence' "$W75"
/usr/bin/grep -q 'state_observation_only' "$W76"
/usr/bin/grep -q 'service_wave76_app import serve' "$LAUNCH"
! /usr/bin/grep -q 'RELEASE_READY = True' "$W69"
! /usr/bin/grep -q 'RELEASE_READY = True' "$W71"
! /usr/bin/grep -q 'RELEASE_READY = True' "$W75"
! /usr/bin/grep -q 'RELEASE_READY = True' "$W76"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$PYTHON" -I -B - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
from unittest.mock import patch

source = Path(sys.argv[1])
data = Path(sys.argv[2]) / "data"
sys.path.insert(0, str(source / "src"))

from binario_marketing.service_wave76_app import AppRuntime
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__

assert __version__ == "0.9.0.dev1", __version__
assert RELEASE_READY is False, RELEASE_READY
assert RELEASE_TAG is None, RELEASE_TAG

runtime = AppRuntime.create(source, data)
try:
    company = runtime.create_company({"name": "Wave 78 Contract Guard"})
    readiness = {
        "manual_scenarios": [
            {
                "id": "journey",
                "title": "Recorrido",
                "required": True,
                "view": "home",
                "precondition": "empresa",
                "expected": "flujo",
            }
        ]
    }
    evidence = {
        "current_build": {
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
            "signing_mode": "ad_hoc",
            "notarized": False,
        },
        "physical_uat": {"accepted_for_current_build": False},
        "release_readiness": {
            "stage": "BLOCKED",
            "production_ready": False,
            "blocker_codes": ["physical_uat_missing", "development_version"],
        },
    }
    canonical_preflight = {
        "schema": "binario.marketing.physical-uat-preflight.v1",
        "ready_to_begin_physical_uat": True,
        "checks": [{"id": "physical-machine", "status": "PASS", "passed": True}],
        "blockers": [],
    }
    with (
        patch.object(runtime, "product_uat_readiness", return_value=readiness),
        patch.object(runtime, "physical_uat_preflight", return_value=canonical_preflight),
        patch.object(runtime, "release_evidence", return_value=evidence),
        patch.object(runtime.physical_uat, "list", return_value=[]),
    ):
        dossier = runtime.candidate_certification_dossier(company["id"])
    assert dossier["stage"] == "READY_FOR_PHYSICAL_UAT", dossier
    assert dossier["preflight"]["ready"] is True, dossier
    assert dossier["release"]["production_ready"] is False, dossier
    assert dossier["governance"]["dossier_is_release_authority"] is False, dossier

    stale_only_preflight = {
        "schema": "binario.marketing.physical-uat-preflight.v1",
        "ready_for_physical_uat": True,
        "checks": [{"id": "physical-machine", "status": "PASS", "passed": True}],
        "blockers": [],
    }
    with (
        patch.object(runtime, "product_uat_readiness", return_value=readiness),
        patch.object(runtime, "physical_uat_preflight", return_value=stale_only_preflight),
        patch.object(runtime, "release_evidence", return_value=evidence),
        patch.object(runtime.physical_uat, "list", return_value=[]),
    ):
        stale_dossier = runtime.candidate_certification_dossier(company["id"])
    assert stale_dossier["stage"] == "BLOCKED_PREFLIGHT", stale_dossier
    assert stale_dossier["preflight"]["ready"] is False, stale_dossier

    sandbox = runtime.create_uat_sandbox({})
    sandbox_company_id = sandbox["company"]["id"]
    try:
        runtime.start_physical_uat(sandbox_company_id, {"operator": "wave78"})
    except ValueError as exc:
        assert "functional-only" in str(exc), exc
    else:
        raise AssertionError("synthetic sandbox unexpectedly accepted physical UAT evidence")
    assert runtime.physical_uat.list(sandbox_company_id) == []
finally:
    if runtime.social_scheduler is not None:
        runtime.social_scheduler.shutdown()
    runtime.proxies.shutdown()
    runtime.transcriptions.shutdown()
    runtime.renders.shutdown()
PY

echo 'WAVE 78 RELEASE CONTRACT DRIFT GUARD PASS'
