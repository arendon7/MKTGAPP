#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave80_x86_runtime_parity.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RES="$APP/Contents/Resources"
SRC="$RES/source"
LAUNCH="$RES/launch.py"
PY="$RES/runtime/python/bin/python3"
PROVENANCE="$RES/BUILD_PROVENANCE.json"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
[[ -f "$LAUNCH" && -x "$PY" && -f "$PROVENANCE" ]]
/usr/bin/grep -q 'service_wave76_app import serve' "$LAUNCH"
! /usr/bin/grep -q 'service_wave77_app import serve' "$LAUNCH"
! /usr/bin/grep -q 'service_wave78_app import serve' "$LAUNCH"

"$PY" -I -B - "$SRC" "$PROVENANCE" "$TMP" <<'PY'
from pathlib import Path
import json
import sys

source = Path(sys.argv[1])
provenance_path = Path(sys.argv[2])
data_root = Path(sys.argv[3]) / "data"
sys.path.insert(0, str(source / "src"))
from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave76_app import AppRuntime
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__

provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
assert provenance["architecture"] == "x86_64", provenance
assert provenance["product_version"] == __version__ == "0.9.0", provenance
assert RELEASE_READY is True
assert RELEASE_TAG == "v0.9.0"
assert source_release_state() == PREPARED_RELEASE
source_readiness = source_release_readiness()
assert source_readiness["source_ready"] is True, source_readiness
assert source_readiness["operational_inputs_complete"] is False, source_readiness
assert source_readiness["production_ready"] is False, source_readiness

runtime = AppRuntime.create(source, data_root)
try:
    company = runtime.create_company({"name": "W80 x86 Runtime Audit"})
    preflight = runtime.physical_uat_preflight(company["id"])
    assert preflight["ready_to_begin_physical_uat"] is False, preflight
    assert "arm64-build" in preflight["blockers"], preflight
    dossier = runtime.candidate_certification_dossier(company["id"])
    assert dossier["stage"] == "BLOCKED_PREFLIGHT", dossier
    assert dossier["release"]["production_ready"] is False, dossier
finally:
    if runtime.social_scheduler is not None:
        runtime.social_scheduler.shutdown()
    runtime.proxies.shutdown()
    runtime.transcriptions.shutdown()
    runtime.renders.shutdown()
PY

/usr/bin/grep -q 'build_full_mac_current_x86_64.sh' "$ROOT/scripts/build_full_mac_release_candidate.sh"
! /usr/bin/grep -q 'scripts/build_full_mac_app.sh --arch' "$ROOT/.github/workflows/persistent-release.yml"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
echo 'WAVE 80 X86_64 CURRENT RUNTIME PARITY AUDIT PASS'
