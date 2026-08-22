#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKFLOW="$ROOT/.github/workflows/persistent-release.yml"
BUILDER="$ROOT/scripts/build_full_mac_release_candidate.sh"
CURRENT="$ROOT/scripts/build_full_mac_current.sh"
GUARDED="$ROOT/scripts/build_full_mac_current_guarded.sh"
X86="$ROOT/scripts/build_full_mac_current_x86_64.sh"

[[ -f "$WORKFLOW" && -f "$BUILDER" && -f "$CURRENT" && -f "$GUARDED" && -f "$X86" ]]
/usr/bin/grep -q 'build_full_mac_release_candidate.sh --arch' "$WORKFLOW"
! /usr/bin/grep -q 'scripts/build_full_mac_app.sh --arch' "$WORKFLOW"
/usr/bin/grep -q 'build_full_mac_current_guarded.sh' "$BUILDER"
/usr/bin/grep -q 'build_full_mac_current_x86_64.sh' "$BUILDER"
/usr/bin/grep -q 'service_wave76_app import serve' "$BUILDER"
/usr/bin/grep -q 'refusing historical fallback' "$BUILDER"
/usr/bin/grep -q 'service_wave76_app import serve' "$CURRENT"
/usr/bin/grep -q 'audit_wave78_release_contract_drift_guard.sh' "$GUARDED"
/usr/bin/grep -q 'canonical current-builder architecture guard drifted' "$X86"
/usr/bin/grep -q 'refusing historical fallback' "$X86"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]

PYTHON_BIN="${PYTHON:-python3}"
PYTHONPATH="$ROOT/src" "$PYTHON_BIN" - <<'PY'
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__
assert __version__ == "0.9.0.dev1", __version__
assert RELEASE_READY is False, RELEASE_READY
assert RELEASE_TAG is None, RELEASE_TAG
PY

echo 'WAVE 79 PERSISTENT RELEASE RUNTIME PARITY AUDIT PASS'
