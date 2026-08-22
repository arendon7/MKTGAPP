#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:?usage: audit_wave88_release_rebuild_semantics.sh <app>}"
RES="$APP/Contents/Resources"
PY="$RES/runtime/python/bin/python3"
MANIFEST="$RES/PHYSICAL_UAT_CANDIDATE.json"
[[ -x "$PY" && -f "$MANIFEST" ]]

"$PY" -I -B -m py_compile "$ROOT/scripts/write_physical_uat_candidate.py" "$ROOT/scripts/release_candidate_gate.py"
"$PY" -I -B - "$ROOT/scripts" "$MANIFEST" <<'PY'
import importlib.util,json,sys
from pathlib import Path
scripts=Path(sys.argv[1]); manifest=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod
writer=load('w88_writer',scripts/'write_physical_uat_candidate.py')
gate=load('w88_gate',scripts/'release_candidate_gate.py')
assert writer._role_for_origin('push','refs/heads/main')==writer.PHYSICAL_ROLE
assert writer._role_for_origin('push','refs/tags/v1.0.0')==writer.DISTRIBUTION_ROLE
assert writer._role_for_origin('pull_request','refs/pull/1/merge')==writer.VALIDATION_ROLE
assert writer._role_for_origin('workflow_dispatch','refs/heads/main')==writer.VALIDATION_ROLE
main=writer._validated_origin({'event':'push','ref':'refs/heads/main','trusted_for_physical_uat':True,'trusted_for_distribution_rebuild':False})
tag=writer._validated_origin({'event':'push','ref':'refs/tags/v1.0.0','trusted_for_physical_uat':False,'trusted_for_distribution_rebuild':True})
assert main['trusted_for_physical_uat'] and not main['trusted_for_distribution_rebuild']
assert tag['trusted_for_distribution_rebuild'] and not tag['trusted_for_physical_uat']
assert manifest['rebuild_semantics_wave']>=88, manifest
assert manifest['release_boundary']['manifest_grants_release_authority'] is False, manifest
assert manifest['physical_uat']['automatic_pass'] is False, manifest
assert 'DISTRIBUTION_REBUILD_ONLY' in (scripts/'release_candidate_gate.py').read_text(encoding='utf-8')
assert 'distribution_rebuild_uat_binding_invalid' in (scripts/'release_candidate_gate.py').read_text(encoding='utf-8')
assert 'physical_candidate_not_distribution_rebuild' in (scripts/'release_candidate_gate.py').read_text(encoding='utf-8')
PY

[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
! /usr/bin/grep -q 'RELEASE_READY = True' "$RES/source/src/binario_marketing/version.py"
echo 'WAVE 88 RELEASE REBUILD SEMANTICS AUDIT PASS'
