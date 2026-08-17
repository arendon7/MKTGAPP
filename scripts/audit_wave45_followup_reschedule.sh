#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/followup-reschedule.js"
SERVICE="$RES/source/src/binario_marketing/service_wave45_app.py"
STORE="$RES/source/src/binario_marketing/crm_store_wave45.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$STORE" && -f "$LOADER" ]] || { echo "Wave 45 audit: reschedule source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave45_app import serve' "$RES/launch.py" || { echo "Wave 45 audit: Mac launch is not using Wave 45" >&2; exit 3; }
for text in 'Reprogramar' 'Guardar fecha' '/reschedule' 'No envía mensajes, correos ni respuestas'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 45 audit: missing explicit reschedule contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q 'due_at must be in the future' "$STORE" || { echo "Wave 45 audit: future-date guard missing" >&2; exit 3; }
/usr/bin/grep -q 'completed activity cannot be rescheduled' "$STORE" || { echo "Wave 45 audit: completed-activity guard missing" >&2; exit 3; }
/usr/bin/grep -q 'crm.activity.rescheduled' "$SERVICE" || { echo "Wave 45 audit: timeline evidence missing" >&2; exit 3; }
/usr/bin/grep -q "reschedule.src='/followup-reschedule.js'" "$LOADER" || { echo "Wave 45 audit: UI loader missing" >&2; exit 3; }
if /usr/bin/grep -Eq '/api/meta/|fetch\(.https://|setInterval\(|MutationObserver\(|publish-now|send-message|auto.?reply' "$UI"; then
  echo "Wave 45 audit: reschedule UI contains provider, background or messaging behavior" >&2; exit 3
fi
POST_COUNT="$(/usr/bin/grep -o "method:'POST'" "$UI" | /usr/bin/wc -l | /usr/bin/tr -d ' ')"
[[ "$POST_COUNT" == "1" ]] || { echo "Wave 45 audit: expected exactly one local POST action, found $POST_COUNT" >&2; exit 3; }
printf 'WAVE 45 FULL MAC FOLLOW-UP RESCHEDULE AUDIT PASS\n'
