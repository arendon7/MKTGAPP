#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/daily-ops.js"
SERVICE="$RES/source/src/binario_marketing/service_wave43_app.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$LOADER" ]] || { echo "Wave 43 audit: daily operations source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave43_app import serve' "$RES/launch.py" || { echo "Wave 43 audit: Mac launch is not using Wave 43" >&2; exit 3; }
for text in 'HOY · PRIORIDADES' 'Qué necesita tu atención' 'REQUIEREN ATENCIÓN' 'Abrir CRM' 'Bandeja'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 43 audit: missing daily focus text: $text" >&2; exit 3; }
done
/usr/bin/grep -q "daily.src='/daily-ops.js'" "$LOADER" || { echo "Wave 43 audit: daily bundle loader missing" >&2; exit 3; }
/usr/bin/grep -q "#editorial-wave42-style" "$LOADER" || { echo "Wave 43 audit: Wave 42 readiness marker missing" >&2; exit 3; }
/usr/bin/grep -q "#inbox-replies-wave41-style" "$LOADER" || { echo "Wave 43 audit: Wave 41 readiness marker missing" >&2; exit 3; }
if /usr/bin/grep -Eq '/api/meta/|fetch\(.https://|method:.POST|method:.DELETE|method:.PATCH|setInterval\(|MutationObserver\(' "$UI"; then
  echo "Wave 43 audit: daily focus contains network/provider mutation or background polling" >&2; exit 3
fi
printf 'WAVE 43 FULL MAC DAILY OPERATIONS AUDIT PASS\n'
