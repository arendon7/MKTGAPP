#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/product-shell.js"
SERVICE="$RES/source/src/binario_marketing/service_wave47_app.py"
BRIDGE="$RES/source/src/binario_marketing/company_workspace.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$BRIDGE" && -f "$LOADER" ]] || { echo "Wave 47 audit: product surface source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave47_app import serve' "$RES/launch.py" || { echo "Wave 47 audit: Mac launch is not using Wave 47" >&2; exit 3; }
for text in 'Video Studio' 'Pauta' 'Empresas & Meta' 'Conectar Meta' 'Crear en Meta · PAUSED' 'Empresa activa'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 47 audit: missing product surface contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q '/api/meta/connection' "$UI" || { echo "Wave 47 audit: direct Meta connection missing" >&2; exit 3; }
/usr/bin/grep -q '/paid-media' "$UI" || { echo "Wave 47 audit: paid-media center missing" >&2; exit 3; }
/usr/bin/grep -q 'company.workspace.created' "$SERVICE" || { echo "Wave 47 audit: company workspace trace missing" >&2; exit 3; }
/usr/bin/grep -q 'safe\["ad_account_id"\] = company.ad_account_id' "$SERVICE" || { echo "Wave 47 audit: company-owned ad-account guard missing" >&2; exit 3; }
/usr/bin/grep -q 'safe\["page_id"\] = company.facebook_page_id' "$SERVICE" || { echo "Wave 47 audit: company-owned page guard missing" >&2; exit 3; }
/usr/bin/grep -q "shell.src='/product-shell.js'" "$LOADER" || { echo "Wave 47 audit: product shell loader missing" >&2; exit 3; }
if /usr/bin/grep -Eqi 'ACTIVE[^A-Za-z]|setInterval\(|auto.?activate|auto.?spend|publish.?automatically' "$UI"; then
  echo "Wave 47 audit: UI appears to contain automatic activation/background behavior" >&2; exit 3
fi
/usr/bin/grep -q 'No se activará gasto' "$UI" || { echo "Wave 47 audit: explicit no-spend confirmation missing" >&2; exit 3; }
printf 'WAVE 47 PRODUCT SURFACE AUDIT PASS\n'
