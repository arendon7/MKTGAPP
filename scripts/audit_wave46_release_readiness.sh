#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
PY="$RES/runtime/python/bin/python3"
PROVENANCE="$RES/BUILD_PROVENANCE.json"
READINESS="$RES/RELEASE_READINESS.json"
TOOLS="$RES/release-tools"
[[ -x "$PY" && -f "$PROVENANCE" && -f "$READINESS" ]] || { echo "Wave 46 audit: release evidence missing" >&2; exit 3; }
for tool in release_candidate_gate.py collect_release_uat.py record_release_uat.py; do
  [[ -f "$TOOLS/$tool" ]] || { echo "Wave 46 audit: bundled release tool missing: $tool" >&2; exit 3; }
done

"$PY" -I -B - "$RES/source/src" "$PROVENANCE" "$READINESS" <<'PY'
import json,sys
from pathlib import Path
src=Path(sys.argv[1]);sys.path.insert(0,str(src))
provenance=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
readiness=json.loads(Path(sys.argv[3]).read_text(encoding='utf-8'))
from binario_marketing.release_readiness import SCHEMA
assert provenance.get('schema') == 'binario.marketing.full-mac-build.v4', provenance
assert readiness.get('schema') == SCHEMA, readiness
assert readiness.get('git_sha') == provenance.get('git_sha'), (readiness, provenance)
assert readiness.get('architecture') == provenance.get('architecture'), (readiness, provenance)
assert readiness.get('signing_mode') == provenance.get('signing_mode'), (readiness, provenance)
assert readiness.get('notarized') is provenance.get('notarized'), (readiness, provenance)
assert readiness.get('uat_passed') is False, readiness
assert readiness.get('production_ready') is False, readiness
assert readiness.get('stage') == 'DEVELOPMENT', readiness
codes=set(readiness.get('blocker_codes') or [])
required={
  'development_version',
  'release_flag_false',
  'release_tag_missing',
  'notarization_missing',
  'physical_uat_missing',
}
assert required.issubset(codes), (codes, required)
mode=provenance.get('signing_mode')
if mode == 'ad_hoc':
    assert 'distribution_signing_missing' in codes, codes
elif mode == 'developer_id':
    assert 'distribution_signing_missing' not in codes, codes
else:
    assert 'distribution_signing_missing' in codes, codes
print('WAVE 46 RELEASE READINESS FAIL-CLOSED PASS')
print(json.dumps({'git_sha':provenance.get('git_sha'),'architecture':provenance.get('architecture'),'signing_mode':mode,'blockers':sorted(codes)},ensure_ascii=False))
PY

GATE_JSON="$(mktemp "${TMPDIR:-/tmp}/wave46-gate.XXXXXX.json")"
trap 'rm -f "$GATE_JSON"' EXIT
"$PY" -I -B "$TOOLS/release_candidate_gate.py" --repo "$RES/source" --app "$APP" --expect-blocked > "$GATE_JSON"
/usr/bin/grep -q '"production_ready": false' "$GATE_JSON" || { cat "$GATE_JSON"; echo "Wave 46 audit: gate did not remain fail-closed" >&2; exit 3; }
/usr/bin/grep -q '"embedded_source_state_matches": true' "$GATE_JSON" || { cat "$GATE_JSON"; echo "Wave 46 audit: embedded candidate state mismatch" >&2; exit 3; }

printf 'WAVE 46 FULL MAC RELEASE READINESS AUDIT PASS\n'
