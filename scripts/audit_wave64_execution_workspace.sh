#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/execution-workspace.js"
SERVICE="$SRC/src/binario_marketing/service_wave64_app.py"
for file in "$UI" "$SERVICE"; do
  [[ -f "$file" ]] || { echo "Wave 64 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave64_app import serve' "$RES/launch.py" || { echo "Wave 64 audit: Mac launch is not using Wave 64" >&2; exit 3; }
/usr/bin/grep -q "execution.src='/execution-workspace.js'" "$SERVICE" || { echo "Wave 64 audit: runtime bootstrap missing execution bundle" >&2; exit 3; }
/usr/bin/grep -q 'data-execution-workspace-wave64' "$SERVICE" || { echo "Wave 64 audit: idempotent bootstrap marker missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave63_app as base' "$SERVICE" || { echo "Wave 64 audit: Wave 63 compatibility base missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.execution-workspace.v1' "$SERVICE" || { echo "Wave 64 audit: schema missing" >&2; exit 3; }
for text in 'Centro de ejecución de campañas' 'De plan a distribución' 'Solo requieren acción' 'Creative Studio' 'Calendario' 'Pauta' 'Resultados'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 64 audit: missing UX contract: $text" >&2; exit 3; }
done
for text in '"provider_read_performed": False' '"provider_mutation_performed": False' '"automatic_publish": False' '"automatic_paid_activation": False' '"automatic_campaign_mutation": False' '"background_polling": False' '"cloud_required": False'; do
  /usr/bin/grep -q "$text" "$SERVICE" || { echo "Wave 64 audit: missing safety contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q '127.0.0.1' "$SERVICE" || { echo "Wave 64 audit: loopback default missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI" "$SERVICE"; then echo "Wave 64 audit: polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 64 audit: UI must not call external endpoints" >&2; exit 3; fi
if /usr/bin/grep -q 'sendBeacon' "$UI"; then echo "Wave 64 audit: beaconing is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q 'def do_POST' "$SERVICE" || /usr/bin/grep -q 'def do_PATCH' "$SERVICE" || /usr/bin/grep -q 'def do_DELETE' "$SERVICE"; then echo "Wave 64 audit: service must not introduce mutation routes" >&2; exit 3; fi
if /usr/bin/grep -Eq "method:[[:space:]]*['\"](POST|PATCH|PUT|DELETE)['\"]" "$UI"; then echo "Wave 64 audit: execution UI must not mutate state directly" >&2; exit 3; fi
if /usr/bin/grep -Eiq 'SUPABASE_[A-Z_]+|VERCEL_[A-Z_]+' "$UI" "$SERVICE"; then echo "Wave 64 audit: execution workspace must not require cloud credentials" >&2; exit 3; fi
printf 'WAVE 64 EXECUTION WORKSPACE AUDIT PASS\n'