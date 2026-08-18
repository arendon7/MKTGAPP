#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/command-center.js"
SERVICE="$RES/source/src/binario_marketing/service_wave50_app.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$LOADER" ]] || { echo "Wave 50 audit: Command Center source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave50_app import serve' "$RES/launch.py" || { echo "Wave 50 audit: Mac launch is not using Wave 50" >&2; exit 3; }
for text in 'MARKETING COMMAND CENTER' 'SIGUIENTE MEJOR ACCIÓN' 'CAMPAIGN COCKPIT' 'READINESS' 'Command Center usa únicamente estado local'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 50 audit: missing product contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "command.src='/command-center.js'" "$LOADER" || { echo "Wave 50 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.command-center.v1' "$SERVICE" || { echo "Wave 50 audit: command-center schema missing" >&2; exit 3; }
/usr/bin/grep -q 'remote_refresh_performed' "$SERVICE" || { echo "Wave 50 audit: local-only safety evidence missing" >&2; exit 3; }
printf 'WAVE 50 COMMAND CENTER AUDIT PASS\n'
