#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/public-gateway.js"
SERVICE="$SRC/src/binario_marketing/service_wave56_app.py"
CLIENT="$SRC/src/binario_marketing/public_gateway.py"
CORE="$SRC/gateway/core.py"
STORAGE="$SRC/gateway/supabase_storage.py"
SQL="$SRC/gateway/supabase/001_public_intake_queue.sql"
VERCEL="$SRC/vercel.json"
KEYCHAIN="$SRC/native/meta_keychain_helper.swift"
LOADER="$SRC/web/audiences-wave39-loader.js"
for file in "$UI" "$SERVICE" "$CLIENT" "$CORE" "$STORAGE" "$SQL" "$VERCEL" "$KEYCHAIN" "$LOADER"; do
  [[ -f "$file" ]] || { echo "Wave 56 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave56_app import serve' "$RES/launch.py" || { echo "Wave 56 audit: Mac launch is not using Wave 56" >&2; exit 3; }
/usr/bin/grep -q "gateway.src='/public-gateway.js'" "$LOADER" || { echo "Wave 56 audit: loader missing public gateway" >&2; exit 3; }
for text in 'Public Intake Gateway' 'Generar y mostrar una vez' 'Revelar secreto del sitio' 'Sincronizar ahora' 'Sin webhook público en el desktop'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 56 audit: missing UI contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q 'binario.marketing.public-gateway-center.v1' "$SERVICE" || { echo "Wave 56 audit: local gateway center schema missing" >&2; exit 3; }
/usr/bin/grep -q 'failed_local_intake_is_not_acked.*True' "$SERVICE" || { echo "Wave 56 audit: failed intake ACK guard missing" >&2; exit 3; }
/usr/bin/grep -q 'master_secret_persisted_in_json.*False' "$SERVICE" || { echo "Wave 56 audit: master secret persistence boundary missing" >&2; exit 3; }
/usr/bin/grep -q 'BINARIO_GATEWAY_MASTER_SECRET' "$CLIENT" || { echo "Wave 56 audit: gateway credential env contract missing" >&2; exit 3; }
/usr/bin/grep -q 'binario-gateway-v1:.*purpose' "$CLIENT" || { echo "Wave 56 audit: tenant-derived secret contract missing" >&2; exit 3; }
/usr/bin/grep -q 'MAX_CLOCK_SKEW_SECONDS = 300' "$CORE" || { echo "Wave 56 audit: replay timestamp window missing" >&2; exit 3; }
/usr/bin/grep -q 'RETENTION_SECONDS = 30 \* 24 \* 3600' "$CORE" || { echo "Wave 56 audit: remote retention contract missing" >&2; exit 3; }
/usr/bin/grep -q 'payloads_redacted.*True' "$CORE" || { echo "Wave 56 audit: ACK redaction contract missing" >&2; exit 3; }
/usr/bin/grep -q 'SUPABASE_SECRET_KEY' "$STORAGE" || { echo "Wave 56 audit: server-side Supabase secret contract missing" >&2; exit 3; }
/usr/bin/grep -qi 'enable row level security' "$SQL" || { echo "Wave 56 audit: RLS missing" >&2; exit 3; }
/usr/bin/grep -q 'revoke all.*anon, authenticated' "$SQL" || { echo "Wave 56 audit: public database roles not revoked" >&2; exit 3; }
/usr/bin/grep -q '"gateway": SecretSlot' "$KEYCHAIN" || { echo "Wave 56 audit: native gateway Keychain namespace missing" >&2; exit 3; }
/usr/bin/grep -q 'api/\*.py' "$VERCEL" || { echo "Wave 56 audit: Vercel Python function packaging missing" >&2; exit 3; }
for endpoint in intake pull ack health; do [[ -f "$SRC/api/$endpoint.py" ]] || { echo "Wave 56 audit: /api/$endpoint deployment entrypoint missing" >&2; exit 3; }; done
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 56 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 56 audit: browser must not call public gateway directly" >&2; exit 3; fi
if /usr/bin/grep -R -q 'SUPABASE_SECRET_KEY.*web/' "$SRC/web" 2>/dev/null; then echo "Wave 56 audit: Supabase secret leaked into browser source" >&2; exit 3; fi
printf 'WAVE 56 PUBLIC INTAKE GATEWAY AUDIT PASS\n'
