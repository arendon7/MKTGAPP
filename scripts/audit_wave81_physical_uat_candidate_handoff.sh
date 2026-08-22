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

"$PY" -I -B - "$MANIFEST" <<'PY'
import json,sys
row=json.load(open(sys.argv[1],encoding='utf-8'))
assert row['schema']=='binario.marketing.physical-uat-candidate.v1', row
assert row['role'] in {'PHYSICAL_UAT_CANDIDATE_ONLY','VALIDATION_BUILD_ONLY'}, row
assert row['architecture']=='arm64', row
assert row['runtime_wave']==76, row
assert row['runtime_entrypoint']=='service_wave76_app', row
assert row['certification_guard_wave']==81, row
assert len(row['candidate_source_sha256'])==64, row
origin=row.get('build_origin') or {}
ref=str(origin.get('ref') or '')
trusted=origin.get('event')=='push' and (ref=='refs/heads/main' or ref.startswith('refs/tags/v'))
assert origin.get('trusted_for_physical_uat') is trusted, row
assert (row['role']=='PHYSICAL_UAT_CANDIDATE_ONLY') is trusted, row
assert row['physical_uat']['eligible_build_origin'] is trusted, row
assert row['release_boundary']['release_ready'] is False, row
assert row['release_boundary']['release_tag'] is None, row
assert row['release_boundary']['production_ready'] is False, row
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
/usr/bin/grep -q 'Automatic PASS: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'service_wave76_app import serve' "$RES/launch.py"
! /usr/bin/grep -q 'RELEASE_READY = True' "$SRC/src/binario_marketing/version.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
echo 'WAVE 81 PHYSICAL UAT CANDIDATE HANDOFF AUDIT PASS'
