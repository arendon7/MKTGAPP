#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/contact-360.js"
SERVICE="$SRC/src/binario_marketing/service_wave62_app.py"
LOADER="$SRC/web/audiences-wave39-loader.js"
for file in "$UI" "$SERVICE" "$LOADER"; do
  [[ -f "$file" ]] || { echo "Wave 62 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave62_app import serve' "$RES/launch.py" || { echo "Wave 62 audit: Mac launch is not using Wave 62" >&2; exit 3; }
/usr/bin/grep -q "contact360.src='/contact-360.js'" "$LOADER" || { echo "Wave 62 audit: loader missing Contact 360" >&2; exit 3; }
/usr/bin/grep -q "commercial.addEventListener('load',loadContact360" "$LOADER" || { echo "Wave 62 audit: Contact 360 must load after Wave 61" >&2; exit 3; }
for text in 'Contacto 360' 'CRM → EVIDENCIA → SIGUIENTE ACCIÓN' 'Origen & atribución' 'Atribución verificada' 'Campañas relacionadas' 'Línea de tiempo' 'Abrir Mesa comercial'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 62 audit: missing UX contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave61_app as base' "$SERVICE" || { echo "Wave 62 audit: Wave 61 compatibility base missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.contact-360.v1' "$SERVICE" || { echo "Wave 62 audit: schema missing" >&2; exit 3; }
/usr/bin/grep -q '"provider_read_performed": False' "$SERVICE" || { echo "Wave 62 audit: provider-read safety missing" >&2; exit 3; }
/usr/bin/grep -q '"automatic_action_execution": False' "$SERVICE" || { echo "Wave 62 audit: automatic action execution must remain disabled" >&2; exit 3; }
/usr/bin/grep -q '"fuzzy_identity_guessing": False' "$SERVICE" || { echo "Wave 62 audit: fuzzy identity guessing must remain disabled" >&2; exit 3; }
/usr/bin/grep -q '"tracking_code_exposed": False' "$SERVICE" || { echo "Wave 62 audit: tracking code must not be exposed" >&2; exit 3; }
/usr/bin/grep -q '"tracked_url_exposed": False' "$SERVICE" || { echo "Wave 62 audit: tracked URL must not be exposed" >&2; exit 3; }
/usr/bin/grep -q '127.0.0.1' "$SERVICE" || { echo "Wave 62 audit: loopback default missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 62 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 62 audit: UI must not call external endpoints" >&2; exit 3; fi
if /usr/bin/grep -q 'social_inbox(' "$SERVICE"; then echo "Wave 62 audit: contact 360 GET must not read Meta Inbox" >&2; exit 3; fi
if /usr/bin/grep -Eiq 'SUPABASE_[A-Z_]+|VERCEL_[A-Z_]+' "$UI" "$SERVICE"; then echo "Wave 62 audit: Contact 360 must not require cloud credentials" >&2; exit 3; fi
printf 'WAVE 62 CONTACT 360 AUDIT PASS\n'