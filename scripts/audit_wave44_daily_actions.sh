#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/daily-actions.js"
SERVICE="$RES/source/src/binario_marketing/service_wave44_app.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$LOADER" ]] || { echo "Wave 44 audit: daily action source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave44_app import serve' "$RES/launch.py" || { echo "Wave 44 audit: Mac launch is not using Wave 44" >&2; exit 3; }
for text in 'Completar' 'Gestionar' 'Ninguna acción publica, reintenta ni responde automáticamente' '/activities/' '/complete'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 44 audit: missing explicit task-resolution contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "actions.src='/daily-actions.js'" "$LOADER" || { echo "Wave 44 audit: action bundle loader missing" >&2; exit 3; }
if /usr/bin/grep -Eq '/api/meta/|fetch\(.https://|setInterval\(|MutationObserver\(|publish-now|retry.*publication' "$UI"; then
  echo "Wave 44 audit: daily actions contain provider mutation, auto-retry or background polling" >&2; exit 3
fi
POST_COUNT="$(/usr/bin/grep -o "method:'POST'" "$UI" | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
[[ "$POST_COUNT" == "1" ]] || { echo "Wave 44 audit: expected exactly one local POST action, found $POST_COUNT" >&2; exit 3; }
printf 'WAVE 44 FULL MAC DAILY ACTIONS AUDIT PASS\n'
