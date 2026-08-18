#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/workdesk.js"
SERVICE="$SRC/src/binario_marketing/service_wave60_app.py"
LOADER="$SRC/web/audiences-wave39-loader.js"
for file in "$UI" "$SERVICE" "$LOADER"; do
  [[ -f "$file" ]] || { echo "Wave 60 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave60_app import serve' "$RES/launch.py" || { echo "Wave 60 audit: Mac launch is not using Wave 60" >&2; exit 3; }
/usr/bin/grep -q "workdesk.src='/workdesk.js'" "$LOADER" || { echo "Wave 60 audit: loader missing workdesk integration" >&2; exit 3; }
/usr/bin/grep -q "local.addEventListener('load',loadWorkdesk" "$LOADER" || { echo "Wave 60 audit: workdesk must load after Wave 59" >&2; exit 3; }
for text in 'MESA DE TRABAJO · W60' 'SIGUIENTE ACCIÓN' 'COLA OPERATIVA' 'Actualizar Inbox' 'Foco comercial' 'Actualizar estado local'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 60 audit: missing UX contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave59_app as base' "$SERVICE" || { echo "Wave 60 audit: Wave 59 compatibility base missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.workdesk.v1' "$SERVICE" || { echo "Wave 60 audit: workdesk schema missing" >&2; exit 3; }
/usr/bin/grep -q '"remote_refresh_performed": False' "$SERVICE" || { echo "Wave 60 audit: explicit remote-read safety missing" >&2; exit 3; }
/usr/bin/grep -q '"provider_mutation_performed": False' "$SERVICE" || { echo "Wave 60 audit: provider mutation safety missing" >&2; exit 3; }
/usr/bin/grep -q '"background_polling": False' "$SERVICE" || { echo "Wave 60 audit: background polling safety missing" >&2; exit 3; }
/usr/bin/grep -q '127.0.0.1' "$SERVICE" || { echo "Wave 60 audit: loopback default missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 60 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 60 audit: workdesk UI must not call external endpoints" >&2; exit 3; fi
if /usr/bin/grep -q '/api/inbox/meta' "$UI" "$SERVICE"; then echo "Wave 60 audit: workdesk must not auto-own Meta Inbox reads" >&2; exit 3; fi
if /usr/bin/grep -Eiq 'SUPABASE_[A-Z_]+|VERCEL_[A-Z_]+' "$UI" "$SERVICE"; then echo "Wave 60 audit: workdesk must not require cloud credentials" >&2; exit 3; fi
printf 'WAVE 60 DAILY WORKDESK AUDIT PASS\n'
