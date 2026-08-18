#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/paid-media-center.js"
SERVICE="$RES/source/src/binario_marketing/service_wave48_app.py"
PLAN="$RES/source/src/binario_marketing/paid_media_plan_store.py"
META="$RES/source/src/binario_marketing/wave48_meta_ads.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$PLAN" && -f "$META" && -f "$LOADER" ]] || { echo "Wave 48 audit: paid-media center source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave48_app import serve' "$RES/launch.py" || { echo "Wave 48 audit: Mac launch is not using Wave 48" >&2; exit 3; }
for text in 'PAID MEDIA CENTER' 'Biblioteca de empresa' 'Campaña de marketing' 'Crear en Meta · PAUSED' 'Actualizar estado y resultados' 'explicit_active_detected'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 48 audit: missing product contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "paid.src='/paid-media-center.js'" "$LOADER" || { echo "Wave 48 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'company_media' "$PLAN" || { echo "Wave 48 audit: managed creative metadata missing" >&2; exit 3; }
/usr/bin/grep -q 'image_hash' "$META" || { echo "Wave 48 audit: image_hash creative missing" >&2; exit 3; }
/usr/bin/grep -q '/adimages' "$META" || { echo "Wave 48 audit: managed image upload missing" >&2; exit 3; }
/usr/bin/grep -q 'status.*PAUSED' "$META" || { echo "Wave 48 audit: scheduled Ad Set PAUSED guard missing" >&2; exit 3; }
/usr/bin/grep -q 'company_paid_media_observability' "$SERVICE" || { echo "Wave 48 audit: remote readback missing" >&2; exit 3; }
/usr/bin/grep -q 'managed.binario.invalid' "$SERVICE" || { echo "Wave 48 audit: managed source legacy placeholder contract missing" >&2; exit 3; }
if /usr/bin/grep -Eq '/activate|setInterval\(|auto.?spend|auto.?activate' "$UI" "$SERVICE" "$META"; then
  echo "Wave 48 audit: activation/background spend behavior detected" >&2; exit 3
fi
printf 'WAVE 48 PAID MEDIA CENTER AUDIT PASS\n'
