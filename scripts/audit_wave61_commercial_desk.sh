#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/commercial-desk.js"
SERVICE="$SRC/src/binario_marketing/service_wave61_app.py"
LOADER="$SRC/web/audiences-wave39-loader.js"
for file in "$UI" "$SERVICE" "$LOADER"; do
  [[ -f "$file" ]] || { echo "Wave 61 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave61_app import serve' "$RES/launch.py" || { echo "Wave 61 audit: Mac launch is not using Wave 61" >&2; exit 3; }
/usr/bin/grep -q "commercial.src='/commercial-desk.js'" "$LOADER" || { echo "Wave 61 audit: loader missing commercial desk" >&2; exit 3; }
/usr/bin/grep -q "workdesk.addEventListener('load',loadCommercialDesk" "$LOADER" || { echo "Wave 61 audit: commercial desk must load after Wave 60" >&2; exit 3; }
for text in 'Mesa comercial' 'INBOX → LEAD → CRM' 'Pasar a Lead Intake' 'Resolver conflicto exacto' 'Crear oportunidad' 'Programar seguimiento' 'Actualizar Inbox'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 61 audit: missing UX contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave60_app as base' "$SERVICE" || { echo "Wave 61 audit: Wave 60 compatibility base missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.commercial-desk.v1' "$SERVICE" || { echo "Wave 61 audit: commercial desk schema missing" >&2; exit 3; }
/usr/bin/grep -q '"exact_identity_only": True' "$SERVICE" || { echo "Wave 61 audit: exact identity gate missing" >&2; exit 3; }
/usr/bin/grep -q '"automatic_merge": False' "$SERVICE" || { echo "Wave 61 audit: automatic merge must remain disabled" >&2; exit 3; }
/usr/bin/grep -q '"provider_read_performed": False' "$SERVICE" || { echo "Wave 61 audit: provider-read safety missing" >&2; exit 3; }
/usr/bin/grep -q '"provider_mutation_performed": False' "$SERVICE" || { echo "Wave 61 audit: provider mutation safety missing" >&2; exit 3; }
/usr/bin/grep -q '"background_polling": False' "$SERVICE" || { echo "Wave 61 audit: background polling safety missing" >&2; exit 3; }
/usr/bin/grep -q '127.0.0.1' "$SERVICE" || { echo "Wave 61 audit: loopback default missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 61 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 61 audit: commercial desk UI must not call external endpoints" >&2; exit 3; fi
if /usr/bin/grep -q 'social_inbox(' "$SERVICE"; then echo "Wave 61 audit: commercial desk GET must not read Meta Inbox" >&2; exit 3; fi
if /usr/bin/grep -Eiq 'SUPABASE_[A-Z_]+|VERCEL_[A-Z_]+' "$UI" "$SERVICE"; then echo "Wave 61 audit: commercial desk must not require cloud credentials" >&2; exit 3; fi
printf 'WAVE 61 COMMERCIAL DESK AUDIT PASS\n'
