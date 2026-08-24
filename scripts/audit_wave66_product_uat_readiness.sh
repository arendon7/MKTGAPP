#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:?usage: audit_wave66_product_uat_readiness.sh <Binario Marketing IA.app>}"
RES="$APP/Contents/Resources"
SRC="$RES/source"
PY="$RES/runtime/python/bin/python3"
SERVICE="$SRC/src/binario_marketing/service_wave66_app.py"
UI="$SRC/web/uat-readiness.js"
LAUNCH="$RES/launch.py"
VERSION="$SRC/src/binario_marketing/version.py"

[[ -x "$PY" && -f "$SERVICE" && -f "$UI" && -f "$LAUNCH" && -f "$VERSION" ]] || {
  echo "Wave 66 audit: required bundled files missing" >&2
  exit 1
}

/usr/bin/grep -q 'binario.marketing.product-uat-readiness.v1' "$SERVICE"
/usr/bin/grep -q 'provider_read_performed.*False' "$SERVICE"
/usr/bin/grep -q 'automatic_publish.*False' "$SERVICE"
/usr/bin/grep -q 'automatic_ad_activation.*False' "$SERVICE"
/usr/bin/grep -q 'cloud_required.*False' "$SERVICE"
/usr/bin/grep -q 'host: str = "127.0.0.1"' "$SERVICE"
/usr/bin/grep -q 'RELEASE_READY' "$SERVICE"
/usr/bin/grep -q 'workflow_names = sorted(_CANONICAL_WORKFLOWS)' "$SERVICE"
! /usr/bin/grep -q '^    def do_POST' "$SERVICE"
! /usr/bin/grep -q '^    def do_PATCH' "$SERVICE"
! /usr/bin/grep -q '^    def do_DELETE' "$SERVICE"

/usr/bin/grep -q 'UAT & Calidad del producto' "$UI"
/usr/bin/grep -q 'TRABAJO DIARIO' "$UI"
/usr/bin/grep -q 'CREAR Y DISTRIBUIR' "$UI"
/usr/bin/grep -q 'MEDIR Y MEJORAR' "$UI"
/usr/bin/grep -q 'Ejecución' "$UI"
/usr/bin/grep -q 'Resultados & IA' "$UI"
/usr/bin/grep -q 'no certifica por sí sola el Mac físico ni producción' "$UI"
! /usr/bin/grep -q 'setInterval' "$UI"
! /usr/bin/grep -q 'sendBeacon' "$UI"
! /usr/bin/grep -q 'supabase' "$UI"
! /usr/bin/grep -q 'vercel' "$UI"

# W66's product-UAT surface must remain valid under both W95 source states.
# A later PREPARED_RELEASE source is not physical-UAT evidence and is never
# production authority by itself.
"$PY" -I -B - "$SRC/src" <<'PY'
from pathlib import Path
import sys

sys.path.insert(0, str(Path(sys.argv[1]).resolve()))
from binario_marketing.release_readiness import LOCKED_SOURCE, PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__

state = source_release_state()
assert state in {LOCKED_SOURCE, PREPARED_RELEASE}, state
report = source_release_readiness()
assert report['production_ready'] is False, report
assert report['operational_inputs_complete'] is False, report
if state == LOCKED_SOURCE:
    assert RELEASE_READY is False
    assert RELEASE_TAG is None
    assert report['source_ready'] is False
else:
    assert RELEASE_READY is True
    assert RELEASE_TAG == f'v{__version__}'
    assert report['source_ready'] is True
    assert report['stage'] == 'SOURCE_CONTRACT_READY', report
print(f'Wave 66 source release contract PASS: {state} / {__version__}')
PY

"$PY" -I -B - "$LAUNCH" <<'PY'
from pathlib import Path
import sys
launch = Path(sys.argv[1]).read_text(encoding='utf-8')
imports = [line.strip() for line in launch.splitlines() if line.startswith('from binario_marketing.service_wave') and line.endswith(' import serve')]
assert imports, imports
assert imports[-1] == 'from binario_marketing.service_wave66_app import serve', imports[-5:]
print('Wave 66 bundled runtime chain PASS')
PY

"$PY" -I -B - "$ROOT/.github/workflows" <<'PY'
from pathlib import Path
import sys
root = Path(sys.argv[1])
workflows = sorted({path.name for pattern in ('*.yml', '*.yaml') for path in root.glob(pattern)})
assert workflows == ['ci.yml', 'full-mac-app.yml', 'persistent-release.yml'], workflows
print('Wave 66 source workflow contract PASS')
PY

printf 'WAVE 66 PRODUCT UAT READINESS AUDIT PASS\n'
