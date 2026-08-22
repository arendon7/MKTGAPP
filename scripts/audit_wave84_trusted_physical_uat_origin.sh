#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave84_trusted_physical_uat_origin.sh <app>}"
RES="$APP/Contents/Resources"
PY="$RES/runtime/python/bin/python3"
MANIFEST="$RES/PHYSICAL_UAT_CANDIDATE.json"
DELIVERY_SCRIPT="$(cd "$(dirname "$0")" && pwd)/package_current_arm64_candidate.py"
SERVICE="$RES/source/src/binario_marketing/service_wave69_app.py"
[[ -x "$PY" && -f "$MANIFEST" && -f "$SERVICE" && -f "$DELIVERY_SCRIPT" ]] || { echo 'Wave 84 origin audit files missing' >&2; exit 1; }
EVENT="${GITHUB_EVENT_NAME:-local}"
REF="${GITHUB_REF:-local}"
"$PY" -I -B - "$MANIFEST" "$EVENT" "$REF" <<'PY'
import json,sys
row=json.load(open(sys.argv[1],encoding='utf-8'))
event=sys.argv[2]; ref=sys.argv[3]
origin=row.get('build_origin') or {}
expected=event=='push' and (ref=='refs/heads/main' or ref.startswith('refs/tags/v'))
assert origin.get('event')==event,(origin,event)
assert origin.get('ref')==ref,(origin,ref)
assert origin.get('trusted_for_physical_uat') is expected,row
assert row.get('role')==('PHYSICAL_UAT_CANDIDATE_ONLY' if expected else 'VALIDATION_BUILD_ONLY'),row
assert row.get('certification_guard_wave')==84,row
assert row.get('physical_uat',{}).get('eligible_build_origin') is expected,row
assert row.get('physical_uat',{}).get('automatic_pass') is False,row
print(f'W84 origin PASS: event={event} ref={ref} trusted={expected}')
PY
/usr/bin/grep -q 'trusted-build-candidate' "$SERVICE"
/usr/bin/grep -q '_require_physical_uat_preflight' "$SERVICE"
/usr/bin/grep -q 'PHYSICAL_UAT_CANDIDATE_ONLY' "$SERVICE"
/usr/bin/grep -q 'VALIDATION_BUILD_ONLY' "$DELIVERY_SCRIPT"
/usr/bin/grep -q 'physical_uat_eligible' "$DELIVERY_SCRIPT"
echo 'WAVE 84 TRUSTED PHYSICAL UAT ORIGIN AUDIT PASS'
