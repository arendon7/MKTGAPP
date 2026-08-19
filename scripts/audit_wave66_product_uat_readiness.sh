#!/bin/bash
set -euo pipefail
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

/usr/bin/grep -q '0.9.0.dev1' "$VERSION"
/usr/bin/grep -q 'RELEASE_READY = False' "$VERSION"

"$PY" -I -B - "$LAUNCH" "$SRC" <<'PY'
from pathlib import Path
import sys
launch = Path(sys.argv[1]).read_text(encoding='utf-8')
source = Path(sys.argv[2])
imports = [line.strip() for line in launch.splitlines() if line.startswith('from binario_marketing.service_wave') and line.endswith(' import serve')]
assert imports, imports
assert imports[-1] == 'from binario_marketing.service_wave66_app import serve', imports[-5:]
workflows = sorted(path.name for path in (source / '.github' / 'workflows').glob('*.yml'))
assert workflows == ['ci.yml', 'full-mac-app.yml', 'persistent-release.yml'], workflows
print('Wave 66 bundled runtime chain + workflow contract PASS')
PY

printf 'WAVE 66 PRODUCT UAT READINESS AUDIT PASS\n'
