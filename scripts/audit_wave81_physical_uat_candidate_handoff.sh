#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:?usage: audit_wave81_physical_uat_candidate_handoff.sh <app>}"
RES="$APP/Contents/Resources"
PY="$RES/runtime/python/bin/python3"
MANIFEST="$RES/PHYSICAL_UAT_CANDIDATE.json"
SUMMARY="$RES/PHYSICAL_UAT_CANDIDATE.md"
[[ -x "$PY" && -f "$MANIFEST" && -f "$SUMMARY" ]]
"$PY" -I -B "$ROOT/scripts/write_physical_uat_candidate.py" --app "$APP" --verify > /tmp/w81-verify.$$.json
trap 'rm -f /tmp/w81-verify.$$.json' EXIT
"$PY" -I -B - "$MANIFEST" <<'PY'
import json,sys
row=json.load(open(sys.argv[1],encoding='utf-8'))
assert row['schema']=='binario.marketing.physical-uat-candidate.v1', row
assert row['role'] in {'PHYSICAL_UAT_CANDIDATE_ONLY','VALIDATION_BUILD_ONLY'}, row
assert row['architecture']=='arm64', row
assert row['runtime_wave']==76, row
assert row['runtime_entrypoint']=='service_wave76_app', row
assert int(row['certification_guard_wave']) >= 81, row
assert int(row.get('source_contract_wave',92)) >= 92, row
assert len(row['candidate_source_sha256'])==64, row
boundary=row['release_boundary']
state=row.get('source_release_state') or boundary.get('source_release_state')
assert state in {'LOCKED_SOURCE','PREPARED_RELEASE'}, row
if state=='LOCKED_SOURCE':
    assert boundary['release_ready'] is False and boundary['release_tag'] is None, row
else:
    assert boundary['release_ready'] is True, row
    assert boundary['release_tag']==f"v{row['product_version']}", row
    assert '.dev' not in row['product_version'].lower() and 'rc' not in row['product_version'].lower(), row
assert boundary.get('operational_authorization') is False, row
assert boundary.get('release_authority') is False, row
assert boundary.get('publication_authority') is False, row
assert boundary['production_ready'] is False, row
assert row['physical_uat']['required'] is True, row
assert row['physical_uat']['automatic_pass'] is False, row
assert row['physical_uat']['eligible_architecture']=='arm64', row
assert row['physical_uat']['evidence_must_match_git_sha'] is True, row
assert row['physical_uat']['evidence_must_match_candidate_source_sha256'] is True, row
assert row['sandbox_boundary']['functional_sandbox_is_release_evidence'] is False, row
assert row['sandbox_boundary']['synthetic_company_is_physical_uat_eligible'] is False, row
PY
/usr/bin/grep -q 'Physical UAT Candidate' "$SUMMARY"
/usr/bin/grep -q 'Release authority: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'Production ready: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'Automatic PASS: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'service_wave76_app import serve' "$RES/launch.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
echo 'WAVE 81/W92 PHYSICAL UAT CANDIDATE HANDOFF AUDIT PASS'
