#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SOURCE="$RES/source"
UI="$SOURCE/web/crm-csv.js"
SERVICE="$SOURCE/src/binario_marketing/service_wave44_app.py"
CSV="$SOURCE/src/binario_marketing/crm_csv.py"
LOADER="$SOURCE/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$CSV" && -f "$LOADER" ]] || { echo "Wave 44 audit: CRM CSV source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave44_app import serve' "$RES/launch.py" || { echo "Wave 44 audit: Mac launch is not using Wave 44" >&2; exit 3; }
for text in 'PORTABILIDAD CRM' 'Previsualizar' 'Importar contactos' 'Exportar CSV'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 44 audit: missing UI action: $text" >&2; exit 3; }
done
/usr/bin/grep -q "csv.src='/crm-csv.js'" "$LOADER" || { echo "Wave 44 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q '#daily-ops-wave43-style' "$LOADER" || { echo "Wave 44 audit: Wave 43 readiness marker missing" >&2; exit 3; }
/usr/bin/grep -q 'MAX_CSV_ROWS = 5_000' "$CSV" || { echo "Wave 44 audit: CSV row limit missing" >&2; exit 3; }
/usr/bin/grep -q 'MAX_CSV_BYTES = 2_000_000' "$CSV" || { echo "Wave 44 audit: CSV byte limit missing" >&2; exit 3; }
/usr/bin/grep -q '\\u200b' "$CSV" || { echo "Wave 44 audit: spreadsheet formula guard missing" >&2; exit 3; }
/usr/bin/grep -q 'import-preview' "$SERVICE" || { echo "Wave 44 audit: preview route missing" >&2; exit 3; }
/usr/bin/grep -q 'text/csv; charset=utf-8' "$SERVICE" || { echo "Wave 44 audit: CSV response content type missing" >&2; exit 3; }
if /usr/bin/grep -Eq 'fetch\(.https://|/api/meta/|setInterval\(|MutationObserver\(' "$UI"; then
  echo "Wave 44 audit: CRM CSV UI contains external provider access or background polling" >&2; exit 3
fi
if /usr/bin/grep -Eq 'access_token|META_ACCESS_TOKEN|recipient_id' "$CSV" "$SERVICE" "$UI"; then
  echo "Wave 44 audit: CRM CSV path references provider credentials/recipient identity" >&2; exit 3
fi
printf 'WAVE 44 FULL MAC CRM CSV AUDIT PASS\n'
