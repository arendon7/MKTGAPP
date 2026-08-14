#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
INBOX="$RES/source/web/inbox.js"
[[ -f "$INBOX" ]] || { echo "Wave 40 audit: inbox.js missing" >&2; exit 3; }
/usr/bin/grep -q 'Crear contacto CRM' "$INBOX" || { echo "Wave 40 audit: CRM contact action missing" >&2; exit 3; }
/usr/bin/grep -q 'Crear seguimiento' "$INBOX" || { echo "Wave 40 audit: CRM follow-up action missing" >&2; exit 3; }
/usr/bin/grep -q 'MKTGAPP_META_' "$INBOX" || { echo "Wave 40 audit: deterministic interaction marker missing" >&2; exit 3; }
/usr/bin/grep -q 'Meta sigue siendo sólo lectura' "$INBOX" || { echo "Wave 40 audit: provider read-only disclosure missing" >&2; exit 3; }
/usr/bin/grep -q "/contacts.*method:'POST'" "$INBOX" || { echo "Wave 40 audit: local CRM contact POST missing" >&2; exit 3; }
/usr/bin/grep -q "/activities.*method:'POST'" "$INBOX" || { echo "Wave 40 audit: local CRM activity POST missing" >&2; exit 3; }
if /usr/bin/grep -q '/api/inbox/meta.*method:' "$INBOX"; then echo "Wave 40 audit: inbox provider route became a mutation" >&2; exit 3; fi
if /usr/bin/grep -Eq "publish-now|sendWhatsApp\(|sendEmail\(|method:'DELETE'|method:'PATCH'|fetch\('https://" "$INBOX"; then echo "Wave 40 audit: forbidden external/provider mutation surface detected" >&2; exit 3; fi
printf 'WAVE 40 FULL MAC CRM TRIAGE AUDIT PASS\n'
