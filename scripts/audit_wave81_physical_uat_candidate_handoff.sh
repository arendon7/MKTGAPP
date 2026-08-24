#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:?usage: audit_wave81_physical_uat_candidate_handoff.sh <app>}"
RES="$APP/Contents/Resources"
SRC="$RES/source"
PY="$RES/runtime/python/bin/python3"
MANIFEST="$RES/PHYSICAL_UAT_CANDIDATE.json"
SUMMARY="$RES/PHYSICAL_UAT_CANDIDATE.md"
[[ -x "$PY" && -f "$MANIFEST" && -f "$SUMMARY" ]]
"$PY" -I -B "$ROOT/scripts/write_physical_uat_candidate.py" --app "$APP" --verify > /tmp/w81-verify.$$.json
trap 'rm -f /tmp/w81-verify.$$.json' EXIT
"$PY" -I -B - "$SRC/src" "$MANIFEST" <<'PY'
import json,sys
from pathlib import Path
src=Path(sys.argv[1]); sys.path.insert(0,str(src))
row=json.load(open(sys.argv[2],encoding='utf-8'))
from binario_marketing.release_readiness import LOCKED_SOURCE, PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__

state=source_release_state()
source_readiness=source_release_readiness()
assert state in {LOCKED_SOURCE, PREPARED_RELEASE}, state
assert source_readiness['production_ready'] is False, source_readiness
assert source_readiness['operational_inputs_complete'] is False, source_readiness

assert row['schema']=='binario.marketing.physical-uat-candidate.v1', row
assert row['role'] in {'PHYSICAL_UAT_CANDIDATE_ONLY','VALIDATION_BUILD_ONLY'}, row
assert row['architecture']=='arm64', row
assert row['runtime_wave']==76, row
assert row['runtime_entrypoint']=='service_wave76_app', row
assert int(row['certification_guard_wave']) >= 81, row
assert row['source_contract_wave']==95, row
assert row['source_release_state']==state, row
assert row['product_version']==__version__, row
assert len(row['candidate_source_sha256'])==64, row
boundary=row['release_boundary']
assert boundary['source_release_state']==state, row
assert boundary['release_ready'] is RELEASE_READY, row
assert boundary['release_tag']==RELEASE_TAG, row
assert boundary['operational_authorization'] is False, row
assert boundary['release_authority'] is False, row
assert boundary['publication_authority'] is False, row
assert boundary['production_ready'] is False, row
if state == LOCKED_SOURCE:
    assert RELEASE_READY is False and RELEASE_TAG is None, row
else:
    assert state == PREPARED_RELEASE, row
    assert RELEASE_READY is True, row
    assert RELEASE_TAG == f'v{__version__}', row
    assert source_readiness['source_ready'] is True, source_readiness
assert row['physical_uat']['required'] is True, row
assert row['physical_uat']['automatic_pass'] is False, row
assert row['physical_uat']['eligible_architecture']=='arm64', row
assert row['physical_uat']['evidence_must_match_git_sha'] is True, row
assert row['physical_uat']['evidence_must_match_candidate_source_sha256'] is True, row
assert row['physical_uat']['prepared_release_required_for_future_production'] is True, row
assert row['sandbox_boundary']['functional_sandbox_is_release_evidence'] is False, row
assert row['sandbox_boundary']['synthetic_company_is_physical_uat_eligible'] is False, row
PY
/usr/bin/grep -q 'Physical UAT Candidate' "$SUMMARY"
/usr/bin/grep -q 'Source contract guard: `Wave 95`' "$SUMMARY"
/usr/bin/grep -q 'Release authority: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'Publication authority: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'Production ready: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'Automatic PASS: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'service_wave76_app import serve' "$RES/launch.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
echo 'WAVE 81 PHYSICAL UAT CANDIDATE HANDOFF AUDIT PASS'
