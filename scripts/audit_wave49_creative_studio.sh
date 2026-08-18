#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/creative-studio-center.js"
SERVICE="$RES/source/src/binario_marketing/service_wave49_app.py"
BRIDGE="$RES/source/src/binario_marketing/creative_bridge_store.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$BRIDGE" && -f "$LOADER" ]] || { echo "Wave 49 audit: creative consolidation source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave49_app import serve' "$RES/launch.py" || { echo "Wave 49 audit: Mac launch is not using Wave 49" >&2; exit 3; }
for text in 'CREATIVE STUDIO' 'Guardar en biblioteca' 'Usar en campaña' 'Usar en Pauta' 'BIBLIOTECA DE EMPRESA'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 49 audit: missing Creative Studio contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "creative.src='/creative-studio-center.js'" "$LOADER" || { echo "Wave 49 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'render SHA-256 no longer matches its certified record' "$SERVICE" || { echo "Wave 49 audit: render tamper guard missing" >&2; exit 3; }
/usr/bin/grep -q 'creative.promoted' "$SERVICE" || { echo "Wave 49 audit: promotion timeline trace missing" >&2; exit 3; }
/usr/bin/grep -q 'campaign.media.attached' "$SERVICE" || { echo "Wave 49 audit: campaign attachment trace missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.creative-bridge.v1' "$BRIDGE" || { echo "Wave 49 audit: provenance schema missing" >&2; exit 3; }
if /usr/bin/grep -Eq 'setInterval\(|/activate|auto.?publish|auto.?spend' "$UI" "$SERVICE"; then
  echo "Wave 49 audit: background/external activation behavior detected" >&2; exit 3
fi
printf 'WAVE 49 CREATIVE STUDIO CONSOLIDATION AUDIT PASS\n'
