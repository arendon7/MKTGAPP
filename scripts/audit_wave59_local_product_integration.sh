#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/local-product-integration.js"
SERVICE="$SRC/src/binario_marketing/service_wave59_app.py"
LOADER="$SRC/web/audiences-wave39-loader.js"
BUILDER="$SRC/scripts/build_full_mac_current.sh"
for file in "$UI" "$SERVICE" "$LOADER" "$BUILDER"; do
  [[ -f "$file" ]] || { echo "Wave 59 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave59_app import serve' "$RES/launch.py" || { echo "Wave 59 audit: Mac launch is not using Wave 59" >&2; exit 3; }
/usr/bin/grep -q "local.src='/local-product-integration.js'" "$LOADER" || { echo "Wave 59 audit: loader missing local integration" >&2; exit 3; }
/usr/bin/grep -q "gateway.addEventListener('load',loadLocalProduct" "$LOADER" || { echo "Wave 59 audit: local integration must load after Wave 56" >&2; exit 3; }
for text in 'Marketing OS local' 'Modo local · datos en este Mac' 'TRABAJO DIARIO' 'CREAR Y DISTRIBUIR' 'Recepción web 24/7' 'No son necesarias para operar la app local' '01 · ATENDER' '06 · APRENDER'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 59 audit: missing product contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave56_app as base' "$SERVICE" || { echo "Wave 59 audit: Wave 56 compatibility base missing" >&2; exit 3; }
/usr/bin/grep -q '/local-product-integration.js' "$SERVICE" || { echo "Wave 59 audit: static route missing" >&2; exit 3; }
/usr/bin/grep -q '127.0.0.1' "$SERVICE" || { echo "Wave 59 audit: loopback default missing" >&2; exit 3; }
/usr/bin/grep -q 'refusing non-loopback bind without --allow-network' "$SERVICE" || { echo "Wave 59 audit: loopback guard missing" >&2; exit 3; }
/usr/bin/grep -q "service_wave56_app','service_wave59_app" "$BUILDER" || { echo "Wave 59 audit: builder ordering missing" >&2; exit 3; }
/usr/bin/grep -q 'audit_wave56_public_gateway.sh' "$BUILDER" || { echo "Wave 59 audit: historical Wave 56 audit missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 59 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 59 audit: local integration must not call external endpoints" >&2; exit 3; fi
if /usr/bin/grep -Eiq 'SUPABASE_[A-Z_]+|VERCEL_[A-Z_]+' "$UI" "$SERVICE"; then echo "Wave 59 audit: local integration must not require cloud credentials" >&2; exit 3; fi
printf 'WAVE 59 LOCAL PRODUCT INTEGRATION AUDIT PASS\n'
