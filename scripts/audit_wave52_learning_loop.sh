#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/learning-loop.js"
SERVICE="$RES/source/src/binario_marketing/service_wave52_app.py"
STORE="$RES/source/src/binario_marketing/learning_store.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$STORE" && -f "$LOADER" ]] || { echo "Wave 52 audit: source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave52_app import serve' "$RES/launch.py" || { echo "Wave 52 audit: Mac launch is not using Wave 52" >&2; exit 3; }
for text in 'ANALYTICS & LEARNING LOOP' 'Actualizar resultados desde Meta' 'DECISIÓN HUMANA' 'NO ATRIBUIDO' 'Registrar decisión local'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 52 audit: missing product contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "learning.src='/learning-loop.js'" "$LOADER" || { echo "Wave 52 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.learning-loop.v1' "$SERVICE" || { echo "Wave 52 audit: learning API schema missing" >&2; exit 3; }
/usr/bin/grep -q 'learning.snapshot.created' "$SERVICE" || { echo "Wave 52 audit: snapshot trace missing" >&2; exit 3; }
/usr/bin/grep -q 'learning.decision.recorded' "$SERVICE" || { echo "Wave 52 audit: decision trace missing" >&2; exit 3; }
/usr/bin/grep -q 'LEARNING_SCHEMA' "$STORE" || { echo "Wave 52 audit: durable learning schema missing" >&2; exit 3; }
printf 'WAVE 52 ANALYTICS LEARNING LOOP AUDIT PASS\n'
