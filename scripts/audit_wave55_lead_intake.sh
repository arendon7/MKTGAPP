#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/lead-intake.js"
SERVICE="$RES/source/src/binario_marketing/service_wave55_app.py"
STORE="$RES/source/src/binario_marketing/lead_intake_store.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$STORE" && -f "$LOADER" ]] || { echo "Wave 55 audit: source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave55_app import serve' "$RES/launch.py" || { echo "Wave 55 audit: Mac launch is not using Wave 55" >&2; exit 3; }
for text in 'Lead Intake & Conversion' 'Registrar lead sin tocar CRM' 'Importar primero a intake' 'Exact identity · no fuzzy'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 55 audit: missing UI contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "lead.src='/lead-intake.js'" "$LOADER" || { echo "Wave 55 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.lead-intake-center.v1' "$SERVICE" || { echo "Wave 55 audit: center API schema missing" >&2; exit 3; }
/usr/bin/grep -q 'ORIGINAL_LEAD_RECEIVED_AT' "$SERVICE" || { echo "Wave 55 audit: attribution time contract missing" >&2; exit 3; }
/usr/bin/grep -q 'exact CRM identity match exists' "$SERVICE" || { echo "Wave 55 audit: duplicate contact guard missing" >&2; exit 3; }
/usr/bin/grep -q 'public_desktop_webhook.*False' "$SERVICE" || { echo "Wave 55 audit: public ingress boundary missing" >&2; exit 3; }
/usr/bin/grep -q 'LEAD_INTAKE_SCHEMA' "$STORE" || { echo "Wave 55 audit: durable schema missing" >&2; exit 3; }
/usr/bin/grep -q 'source_ref already exists with a different lead payload' "$STORE" || { echo "Wave 55 audit: idempotency fail-closed guard missing" >&2; exit 3; }
/usr/bin/grep -q 'name_fuzzy_matching.*False' "$SERVICE" || { echo "Wave 55 audit: no-fuzzy contract missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 55 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 55 audit: external browser fetch is forbidden" >&2; exit 3; fi
printf 'WAVE 55 LEAD INTAKE & CONVERSION AUDIT PASS\n'
