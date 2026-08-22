#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:?usage: audit_wave85_dual_physical_evidence_gate.sh <app>}"
RES="$APP/Contents/Resources"
PY="$RES/runtime/python/bin/python3"
MANIFEST="$RES/PHYSICAL_UAT_CANDIDATE.json"
[[ -x "$PY" && -f "$MANIFEST" ]]

"$PY" -I -B -m py_compile "$ROOT/scripts/collect_product_uat.py" "$ROOT/scripts/release_candidate_gate.py" "$ROOT/scripts/verify_physical_uat_handoff.py" "$ROOT/scripts/package_current_arm64_candidate.py"
/bin/bash -n "$ROOT/scripts/collect_product_uat.command"

"$PY" -I -B - "$MANIFEST" "$ROOT/scripts/release_candidate_gate.py" "$ROOT/scripts/package_current_arm64_candidate.py" <<'PY'
import json,sys
from pathlib import Path
manifest=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
gate=Path(sys.argv[2]).read_text(encoding='utf-8')
pack=Path(sys.argv[3]).read_text(encoding='utf-8')
assert manifest['runtime_wave']==76, manifest
assert manifest['certification_guard_wave']==84, manifest
assert manifest['release_boundary']['release_ready'] is False, manifest
assert manifest['release_boundary']['release_tag'] is None, manifest
assert manifest['release_boundary']['production_ready'] is False, manifest
for marker in ('--product-uat-evidence','physical_product_uat_missing_or_invalid','release_operational_uat_missing_or_invalid','dual_physical_uat_binding_mismatch','dual_physical_uat_passed'):
    assert marker in gate, marker
for marker in ('DUAL_EVIDENCE_GUARD_WAVE = 85','PRODUCT_UAT_COLLECT.py','COLLECT_PRODUCT_UAT.command','dual_physical_uat_required'):
    assert marker in pack, marker
PY

[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
! /usr/bin/grep -q 'RELEASE_READY = True' "$RES/source/src/binario_marketing/version.py"
echo 'WAVE 85 DUAL PHYSICAL EVIDENCE GATE AUDIT PASS'
