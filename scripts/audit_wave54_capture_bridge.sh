#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/capture-bridge.js"
PORTABLE="$RES/source/web/first-party-capture-bridge.js"
SERVICE="$RES/source/src/binario_marketing/service_wave54_app.py"
STORE="$RES/source/src/binario_marketing/capture_store.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$PORTABLE" && -f "$SERVICE" && -f "$STORE" && -f "$LOADER" ]] || { echo "Wave 54 audit: source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave54_app import serve' "$RES/launch.py" || { echo "Wave 54 audit: Mac launch is not using Wave 54" >&2; exit 3; }
for text in 'Capture Bridge' 'Descargar JS portable' 'Del formulario al CRM' 'Server receive time'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 54 audit: missing UI contract: $text" >&2; exit 3; }
done
for text in 'sessionStorage' 'MutationObserver' 'bm_tid' 'bm_client_captured_at' 'binario:attribution-captured'; do
  /usr/bin/grep -q "$text" "$PORTABLE" || { echo "Wave 54 audit: portable bridge missing: $text" >&2; exit 3; }
done
/usr/bin/grep -q "capture.src='/capture-bridge.js'" "$LOADER" || { echo "Wave 54 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.first-party-capture-bridge.v1' "$SERVICE" || { echo "Wave 54 audit: API schema missing" >&2; exit 3; }
/usr/bin/grep -q 'captured .* does not match canonical tracking link' "$SERVICE" || { echo "Wave 54 audit: canonical UTM fail-closed guard missing" >&2; exit 3; }
/usr/bin/grep -q 'browser_timestamp_authoritative.*False' "$SERVICE" || { echo "Wave 54 audit: server-time evidence contract missing" >&2; exit 3; }
/usr/bin/grep -q 'FIRST_PARTY_CAPTURE_SCHEMA' "$STORE" || { echo "Wave 54 audit: durable capture schema missing" >&2; exit 3; }
/usr/bin/grep -q 'full referrer' "$STORE" || { echo "Wave 54 audit: PII-minimization contract missing" >&2; exit 3; }
for forbidden in 'setInterval' 'XMLHttpRequest' 'sendBeacon' 'requestSubmit' '.submit('; do
  if /usr/bin/grep -q "$forbidden" "$PORTABLE"; then echo "Wave 54 audit: portable bridge forbidden behavior: $forbidden" >&2; exit 3; fi
done
if /usr/bin/grep -q 'fetch(' "$PORTABLE"; then echo "Wave 54 audit: portable bridge must not make network calls" >&2; exit 3; fi
printf 'WAVE 54 FIRST-PARTY CAPTURE BRIDGE AUDIT PASS\n'
