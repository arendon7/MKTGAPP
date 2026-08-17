#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SOURCE="$RES/source"
UI="$SOURCE/web/editorial-management.js"
SERVICE="$SOURCE/src/binario_marketing/service_wave42_app.py"
[[ -f "$UI" && -f "$SERVICE" ]] || { echo "Wave 42 audit: editorial source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave42_app import serve' "$RES/launch.py" || { echo "Wave 42 audit: Mac launch is not using Wave 42" >&2; exit 3; }
/usr/bin/grep -q 'Guardar nueva versión' "$UI" || { echo "Wave 42 audit: revision action missing" >&2; exit 3; }
/usr/bin/grep -q 'Cancelar publicación' "$UI" || { echo "Wave 42 audit: cancel action missing" >&2; exit 3; }
/usr/bin/grep -q '/replace' "$UI" || { echo "Wave 42 audit: replacement route missing from UI" >&2; exit 3; }
/usr/bin/grep -q 'allowed = {"message", "scheduled_for"}' "$SERVICE" || { echo "Wave 42 audit: revision allowlist missing" >&2; exit 3; }
/usr/bin/grep -q 'company.publication.replaced' "$SERVICE" || { echo "Wave 42 audit: replacement timeline event missing" >&2; exit 3; }
/usr/bin/grep -q 'current.status not in {"DRAFT", "QUEUED", "FAILED"}' "$SERVICE" || { echo "Wave 42 audit: immutable terminal-state guard missing" >&2; exit 3; }
if /usr/bin/grep -Eq 'target_id|target_name|channel:|kind:|asset_id|render_id|media_url|link_url' "$UI"; then echo "Wave 42 audit: browser can mutate immutable publication identity/media" >&2; exit 3; fi
if /usr/bin/grep -Eq 'setInterval\(|MutationObserver\(' "$UI"; then echo "Wave 42 audit: automatic editorial mutation detected" >&2; exit 3; fi
printf 'WAVE 42 FULL MAC EDITORIAL MANAGEMENT AUDIT PASS\n'
