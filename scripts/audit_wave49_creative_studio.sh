#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/creative-studio.js"
SERVICE="$RES/source/src/binario_marketing/service_wave49_app.py"
STORE="$RES/source/src/binario_marketing/creative_store.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$STORE" && -f "$LOADER" ]] || { echo "Wave 49 audit: Creative Studio source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave49_app import serve' "$RES/launch.py" || { echo "Wave 49 audit: Mac launch is not using Wave 49" >&2; exit 3; }
for text in 'Pipeline creativo' 'Enviar a Creative Studio' 'Preparar Facebook' 'Preparar Instagram' 'Enviar a Pauta' 'Biblioteca / importar'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 49 audit: missing product contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "creative.src='/creative-studio.js'" "$LOADER" || { echo "Wave 49 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'creative.render.promoted' "$SERVICE" || { echo "Wave 49 audit: render promotion trace missing" >&2; exit 3; }
/usr/bin/grep -q 'creative.publication.prepared' "$SERVICE" || { echo "Wave 49 audit: publication bridge missing" >&2; exit 3; }
/usr/bin/grep -q 'creative.paid_media.linked' "$SERVICE" || { echo "Wave 49 audit: paid-media bridge missing" >&2; exit 3; }
/usr/bin/grep -q 'CREATIVE_SCHEMA' "$STORE" || { echo "Wave 49 audit: creative store schema missing" >&2; exit 3; }
printf 'WAVE 49 CREATIVE STUDIO AUDIT PASS\n'
