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
assert row['role'] in {'PHYSICAL_UAT_CANDIDATE_ONLY','DISTRIBUTION_REBUILD_ONLY','VALIDATION_BUILD_ONLY'}, row
assert row['architecture']=='arm64', row
assert row['runtime_wave']==76, row
assert row['runtime_entrypoint']=='service_wave76_app', row
assert int(row['certification_guard_wave']) >= 81, row
assert int(row.get('rebuild_semantics_wave') or 0) >= 88, row
assert len(row['candidate_source_sha256'])==64, row
assert row['release_boundary']['production_ready'] is False, row
assert row['release_boundary']['manifest_grants_release_authority'] is False, row
assert row['physical_uat']['required'] is True, row
assert row['physical_uat']['automatic_pass'] is False, row
assert row['physical_uat']['eligible_architecture']=='arm64', row
assert row['physical_uat']['evidence_must_match_git_sha'] is True, row
assert row['physical_uat']['evidence_must_match_candidate_source_sha256'] is True, row
assert row['sandbox_boundary']['functional_sandbox_is_release_evidence'] is False, row
assert row['sandbox_boundary']['synthetic_company_is_physical_uat_eligible'] is False, row
origin=row['build_origin']; role=row['role']; physical=row['physical_uat']; distribution=row['distribution_rebuild']
if role=='PHYSICAL_UAT_CANDIDATE_ONLY':
    assert origin['event']=='push' and origin['ref']=='refs/heads/main', row
    assert origin['trusted_for_physical_uat'] is True, row
    assert origin['trusted_for_distribution_rebuild'] is False, row
    assert physical['eligible_build_origin'] is True and physical['new_evidence_may_be_recorded'] is True, row
    assert distribution['eligible_build_origin'] is False, row
    assert row['release_boundary']['release_ready'] is False and row['release_boundary']['release_tag'] is None, row
elif role=='DISTRIBUTION_REBUILD_ONLY':
    assert origin['event']=='push' and origin['ref'].startswith('refs/tags/v'), row
    assert origin['trusted_for_physical_uat'] is False, row
    assert origin['trusted_for_distribution_rebuild'] is True, row
    assert physical['eligible_build_origin'] is False and physical['new_evidence_may_be_recorded'] is False, row
    assert physical['source_equivalent_prior_evidence_allowed'] is True, row
    assert distribution['eligible_build_origin'] is True, row
    assert distribution['must_not_record_new_physical_uat'] is True, row
    assert distribution['requires_prior_combined_uat_attestation'] is True, row
    assert distribution['requires_distribution_trust_evidence'] is True, row
    assert distribution['release_authority'] is False, row
else:
    assert origin['trusted_for_physical_uat'] is False, row
    assert origin['trusted_for_distribution_rebuild'] is False, row
    assert physical['eligible_build_origin'] is False and physical['new_evidence_may_be_recorded'] is False, row
    assert distribution['eligible_build_origin'] is False, row
PY
/usr/bin/grep -q 'Build Role Manifest' "$SUMMARY"
/usr/bin/grep -q 'Release authority from this manifest: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'Automatic UAT PASS: \*\*NO\*\*' "$SUMMARY"
/usr/bin/grep -q 'service_wave76_app import serve' "$RES/launch.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
echo 'WAVE 81 PHYSICAL UAT / DISTRIBUTION ROLE AUDIT PASS'
