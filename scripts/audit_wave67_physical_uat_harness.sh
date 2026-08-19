#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:?usage: audit_wave67_physical_uat_harness.sh <Binario Marketing IA.app>}"
RES="$APP/Contents/Resources"
SRC="$RES/source"
PY="$RES/runtime/python/bin/python3"
SERVICE="$SRC/src/binario_marketing/service_wave67_app.py"
STORE="$SRC/src/binario_marketing/physical_uat_store.py"
UI="$SRC/web/physical-uat.js"
LAUNCH="$RES/launch.py"
VERSION="$SRC/src/binario_marketing/version.py"

[[ -x "$PY" && -f "$SERVICE" && -f "$STORE" && -f "$UI" && -f "$LAUNCH" && -f "$VERSION" ]] || {
  echo "Wave 67 audit: required bundled files missing" >&2
  exit 1
}

/usr/bin/grep -q 'binario.marketing.physical-uat-evidence.v1' "$STORE"
/usr/bin/grep -q 'physical_gate_eligible' "$STORE"
/usr/bin/grep -q 'GITHUB_ACTIONS' "$STORE"
/usr/bin/grep -q 'physical_uat_complete' "$STORE"
/usr/bin/grep -q 'write_json_atomic' "$STORE"
/usr/bin/grep -q 'required UAT scenario cannot be skipped' "$STORE"

/usr/bin/grep -q 'physical_uat_overview' "$SERVICE"
/usr/bin/grep -q 'marketing_mutation_performed.*False' "$SERVICE"
/usr/bin/grep -q 'provider_mutation_performed.*False' "$SERVICE"
/usr/bin/grep -q 'release_ready_changed.*False' "$SERVICE"
/usr/bin/grep -q 'physical.src='"'"'/physical-uat.js'"'"'' "$SERVICE"
/usr/bin/grep -q 'host: str = "127.0.0.1"' "$SERVICE"

/usr/bin/grep -q 'Evidencia de prueba en Mac físico' "$UI"
/usr/bin/grep -q 'CI nunca podrá satisfacer el gate físico' "$UI"
/usr/bin/grep -q "method:'POST'" "$UI"
/usr/bin/grep -q "method:'PATCH'" "$UI"
/usr/bin/grep -q 'Exportar JSON' "$UI"
! /usr/bin/grep -q 'setInterval' "$UI"
! /usr/bin/grep -q 'sendBeacon' "$UI"
! /usr/bin/grep -q "fetch('https://" "$UI"
! /usr/bin/grep -qi 'supabase' "$UI"
! /usr/bin/grep -qi 'vercel' "$UI"
! /usr/bin/grep -q '/opportunities' "$UI"
! /usr/bin/grep -q '/publications' "$UI"
! /usr/bin/grep -q '/paid-media' "$UI"

/usr/bin/grep -q '0.9.0.dev1' "$VERSION"
/usr/bin/grep -q 'RELEASE_READY = False' "$VERSION"

"$PY" -I -B - "$LAUNCH" <<'PY'
from pathlib import Path
import sys
launch = Path(sys.argv[1]).read_text(encoding='utf-8')
imports = [line.strip() for line in launch.splitlines() if line.startswith('from binario_marketing.service_wave') and line.endswith(' import serve')]
assert imports, imports
assert imports[-1] == 'from binario_marketing.service_wave67_app import serve', imports[-5:]
print('Wave 67 bundled runtime chain PASS')
PY

"$PY" -I -B - "$ROOT/.github/workflows" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
workflows = sorted({path.name for pattern in ('*.yml', '*.yaml') for path in root.glob(pattern)})
assert workflows == ['ci.yml', 'full-mac-app.yml', 'persistent-release.yml'], workflows
print('Wave 67 source workflow contract PASS')
PY

printf 'WAVE 67 PHYSICAL UAT EVIDENCE HARNESS AUDIT PASS\n'
