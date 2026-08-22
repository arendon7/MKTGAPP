#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave81_main_physical_uat_candidate.sh <app>}"
RES="$APP/Contents/Resources"
PROVENANCE="$RES/BUILD_PROVENANCE.json"
SERVICE="$RES/source/src/binario_marketing/service_wave69_app.py"
PY="$RES/runtime/python/bin/python3"
[[ -f "$PROVENANCE" && -f "$SERVICE" && -x "$PY" ]] || { echo 'Wave 81 candidate audit files missing' >&2; exit 1; }

EVENT="${GITHUB_EVENT_NAME:-local}"
REF="${GITHUB_REF:-local}"
"$PY" -I -B - "$PROVENANCE" "$EVENT" "$REF" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
event = sys.argv[2]
ref = sys.argv[3]
row = json.loads(path.read_text(encoding="utf-8"))
expected = event == "push" and ref == "refs/heads/main" and row.get("architecture") == "arm64"
assert row.get("build_event") == event, row
assert row.get("build_ref") == ref, row
assert row.get("physical_uat_candidate") is expected, row
assert row.get("release_channel") == "development", row
assert row.get("notarized") is False, row
print(f"W81 provenance: event={event} ref={ref} physical_uat_candidate={expected}")
PY

/usr/bin/grep -q 'main-candidate-build' "$SERVICE"
/usr/bin/grep -q 'physical_uat_candidate' "$SERVICE"
/usr/bin/grep -q '_require_physical_uat_preflight' "$SERVICE"
/usr/bin/grep -q 'physical UAT preflight blocked' "$SERVICE"
echo 'WAVE 81 MAIN PHYSICAL UAT CANDIDATE AUDIT PASS'
