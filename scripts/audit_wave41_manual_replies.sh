#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SOURCE="$RES/source"
UI="$SOURCE/web/inbox-replies.js"
SERVICE="$SOURCE/src/binario_marketing/service_wave41_app.py"
WRITER="$SOURCE/src/binario_marketing/meta_inbox_actions.py"
STORE="$SOURCE/src/binario_marketing/inbox_reply_store.py"
[[ -f "$UI" && -f "$SERVICE" && -f "$WRITER" && -f "$STORE" ]] || { echo "Wave 41 audit: reply source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave41_app import serve' "$RES/launch.py" || { echo "Wave 41 audit: Mac launch is not using Wave 41" >&2; exit 3; }
/usr/bin/grep -q '/inbox/reply' "$UI" || { echo "Wave 41 audit: explicit reply API missing from UI" >&2; exit 3; }
/usr/bin/grep -q 'Enviar respuesta' "$UI" || { echo "Wave 41 audit: explicit send confirmation missing" >&2; exit 3; }
/usr/bin/grep -q 'messaging_type' "$WRITER" || { echo "Wave 41 audit: Messenger response contract missing" >&2; exit 3; }
/usr/bin/grep -q '/replies' "$WRITER" || { echo "Wave 41 audit: Instagram public comment reply contract missing" >&2; exit 3; }
/usr/bin/grep -q 'AMBIGUOUS' "$STORE" || { echo "Wave 41 audit: ambiguous provider checkpoint missing" >&2; exit 3; }
if /usr/bin/grep -Eq 'recipient_id|access_token|page_id|instagram_id|fetch\(.https://' "$UI"; then echo "Wave 41 audit: browser can influence provider identity or credentials" >&2; exit 3; fi
if /usr/bin/grep -Eq 'setInterval\(|MutationObserver\(|method:.DELETE|method:.PATCH' "$UI"; then echo "Wave 41 audit: automatic or moderation mutation detected" >&2; exit 3; fi
/usr/bin/grep -q 'allowed = {"kind", "interaction_id", "text"}' "$SERVICE" || { echo "Wave 41 audit: server reply payload allowlist missing" >&2; exit 3; }
printf 'WAVE 41 FULL MAC MANUAL REPLY AUDIT PASS\n'
