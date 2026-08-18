#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/attribution-foundation.js"
SERVICE="$RES/source/src/binario_marketing/service_wave53_app.py"
STORE="$RES/source/src/binario_marketing/attribution_store.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$STORE" && -f "$LOADER" ]] || { echo "Wave 53 audit: source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave53_app import serve' "$RES/launch.py" || { echo "Wave 53 audit: Mac launch is not using Wave 53" >&2; exit 3; }
for text in 'Attribution Foundation' 'Crear enlace con UTM + bm_tid' 'Vincular bm_tid capturado' 'LAST_CAPTURED_TOUCH' 'Generar el enlace no registra un clic'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 53 audit: missing UI contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "attribution.src='/attribution-foundation.js'" "$LOADER" || { echo "Wave 53 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.attribution-foundation.v1' "$SERVICE" || { echo "Wave 53 audit: API schema missing" >&2; exit 3; }
/usr/bin/grep -q 'attribution.tracking_link.created' "$SERVICE" || { echo "Wave 53 audit: tracking trace missing" >&2; exit 3; }
/usr/bin/grep -q 'attribution.claim.recorded' "$SERVICE" || { echo "Wave 53 audit: claim trace missing" >&2; exit 3; }
/usr/bin/grep -q 'TRACKING_LINK_SCHEMA' "$STORE" || { echo "Wave 53 audit: durable schema missing" >&2; exit 3; }
/usr/bin/grep -q 'CAPTURED_TRACKING_CODE' "$STORE" || { echo "Wave 53 audit: evidence contract missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 53 audit: background polling is forbidden" >&2; exit 3; fi
printf 'WAVE 53 ATTRIBUTION FOUNDATION AUDIT PASS\n'