#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/commercial-pipeline.js"
SERVICE="$SRC/src/binario_marketing/service_wave63_app.py"
for file in "$UI" "$SERVICE"; do
  [[ -f "$file" ]] || { echo "Wave 63 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave63_app import serve' "$RES/launch.py" || { echo "Wave 63 audit: Mac launch is not using Wave 63" >&2; exit 3; }
/usr/bin/grep -q "pipeline.src='/commercial-pipeline.js'" "$SERVICE" || { echo "Wave 63 audit: runtime bootstrap missing pipeline bundle" >&2; exit 3; }
/usr/bin/grep -q "data-commercial-pipeline-wave63" "$SERVICE" || { echo "Wave 63 audit: idempotent browser bootstrap missing" >&2; exit 3; }
for text in 'Pipeline comercial operativo' 'Valores separados por moneda' 'Solo requieren atención' 'Guardar etapa' 'Contacto 360' "method:'PATCH'"; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 63 audit: missing UX contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "select.addEventListener('change'" "$UI" || { echo "Wave 63 audit: stage selector missing" >&2; exit 3; }
/usr/bin/grep -q "save.addEventListener('click'" "$UI" || { echo "Wave 63 audit: explicit stage save missing" >&2; exit 3; }
/usr/bin/grep -q "window.confirm" "$UI" || { echo "Wave 63 audit: terminal stage confirmation missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave62_app as base' "$SERVICE" || { echo "Wave 63 audit: Wave 62 compatibility base missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.commercial-pipeline.v1' "$SERVICE" || { echo "Wave 63 audit: schema missing" >&2; exit 3; }
/usr/bin/grep -q '"provider_read_performed": False' "$SERVICE" || { echo "Wave 63 audit: provider-read safety missing" >&2; exit 3; }
/usr/bin/grep -q '"automatic_stage_change": False' "$SERVICE" || { echo "Wave 63 audit: automatic stage changes must remain disabled" >&2; exit 3; }
/usr/bin/grep -q '"mixed_currency_aggregation": False' "$SERVICE" || { echo "Wave 63 audit: mixed currency aggregation must remain disabled" >&2; exit 3; }
/usr/bin/grep -q '"explicit_save_required": True' "$SERVICE" || { echo "Wave 63 audit: explicit stage save contract missing" >&2; exit 3; }
/usr/bin/grep -q '127.0.0.1' "$SERVICE" || { echo "Wave 63 audit: loopback default missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI" "$SERVICE"; then echo "Wave 63 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 63 audit: UI must not call external endpoints" >&2; exit 3; fi
if /usr/bin/grep -q 'sendBeacon' "$UI"; then echo "Wave 63 audit: browser beaconing is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q 'social_inbox(' "$SERVICE"; then echo "Wave 63 audit: pipeline GET must not read Meta Inbox" >&2; exit 3; fi
if /usr/bin/grep -q 'def do_POST' "$SERVICE" || /usr/bin/grep -q 'def do_PATCH' "$SERVICE"; then echo "Wave 63 audit: service must not introduce mutation routes" >&2; exit 3; fi
if /usr/bin/grep -Eiq 'SUPABASE_[A-Z_]+|VERCEL_[A-Z_]+' "$UI" "$SERVICE"; then echo "Wave 63 audit: pipeline must not require cloud credentials" >&2; exit 3; fi
printf 'WAVE 63 COMMERCIAL PIPELINE AUDIT PASS\n'