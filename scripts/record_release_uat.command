#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
WORK="$ROOT/PHYSICAL_UAT_WORK"
APP="$WORK/Binario Marketing IA.app"
EVIDENCE="$ROOT/PHYSICAL_UAT_EVIDENCE/release-uat-evidence.json"
VERIFY="$ROOT/PHYSICAL_UAT_HANDOFF_VERIFY.py"
fail(){ printf 'RELEASE UAT RECORD BLOCKED: %s\n' "$1" >&2; exit 4; }

[[ "$(uname -s)" == "Darwin" ]] || fail "this recorder must run on macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "physical UAT requires an Apple Silicon arm64 Mac"
[[ "${GITHUB_ACTIONS:-}" != "true" && "${CI:-}" != "true" ]] || fail "physical UAT cannot run in CI"
[[ -d "$APP" ]] || fail "run START_PHYSICAL_UAT.command first"
[[ -f "$EVIDENCE" ]] || fail "release UAT evidence is not initialized; run START_PHYSICAL_UAT.command first"
[[ -f "$VERIFY" ]] || fail "handoff verifier missing"

PY="$APP/Contents/Resources/runtime/python/bin/python3"
RECORDER="$APP/Contents/Resources/release-tools/record_release_uat.py"
[[ -x "$PY" ]] || fail "embedded Python runtime missing"
[[ -f "$RECORDER" ]] || fail "embedded release UAT recorder missing"

/usr/bin/codesign --verify --deep --strict "$APP" || fail "candidate bundle signature drift detected"
"$PY" -I -B "$VERIFY" --delivery-dir "$ROOT" --app "$APP" --require-physical-host >/dev/null

"$PY" -I -B - "$EVIDENCE" <<'PY'
import json,sys
from pathlib import Path
row=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
print('\nBINARIO Marketing IA · Release UAT manual gates')
print('Candidate:', row.get('git_sha'))
print('Overall:', row.get('overall'))
print('')
for item in row.get('manual_steps') or []:
    print(f"[{item.get('status','PENDING'):7}] {item.get('id')}: {item.get('step')}")
PY

printf '\nID exacto del gate a registrar: '
IFS= read -r STEP
[[ -n "$STEP" ]] || fail "gate id is required"
printf 'Resultado (PASS o FAIL): '
IFS= read -r STATUS
STATUS="$(printf '%s' "$STATUS" | /usr/bin/tr '[:lower:]' '[:upper:]')"
[[ "$STATUS" == "PASS" || "$STATUS" == "FAIL" ]] || fail "status must be PASS or FAIL"
printf 'Nota concreta de evidencia/observación: '
IFS= read -r NOTE
[[ -n "${NOTE//[[:space:]]/}" ]] || fail "a concrete evidence note is required"

set +e
"$PY" -I -B "$RECORDER" \
  --evidence "$EVIDENCE" \
  --step "$STEP" \
  --status "$STATUS" \
  --note "$NOTE"
RC=$?
set -e

"$PY" -I -B - "$EVIDENCE" <<'PY'
import json,sys
from pathlib import Path
row=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
pending=[item.get('id') for item in row.get('manual_steps') or [] if item.get('status') == 'PENDING']
failed=[item.get('id') for item in row.get('manual_steps') or [] if item.get('status') == 'FAIL']
print('\nCurrent overall:', row.get('overall'))
print('UAT passed:', bool(row.get('uat_passed')))
print('Pending gates:', ', '.join(pending) if pending else 'none')
print('Failed gates:', ', '.join(failed) if failed else 'none')
if row.get('uat_passed') is True:
    print('\nRELEASE UAT MANUAL GATES COMPLETE: UAT_PASS')
    print('This is evidence only. It does NOT enable release, signing, notarization or a tag.')
PY

exit "$RC"
