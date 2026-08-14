#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
PY="$RES/runtime/python/bin/python3"
[[ -x "$PY" ]] || { echo "Wave 39 audit: embedded Python missing" >&2; exit 3; }
[[ -f "$RES/source/src/binario_marketing/meta_inbox.py" ]] || { echo "Wave 39 audit: meta_inbox.py missing" >&2; exit 3; }
[[ -f "$RES/source/src/binario_marketing/service_wave39_app.py" ]] || { echo "Wave 39 audit: service_wave39_app.py missing" >&2; exit 3; }
[[ -f "$RES/source/web/audiences-wave39-loader.js" ]] || { echo "Wave 39 audit: loader missing" >&2; exit 3; }
[[ -f "$RES/source/web/inbox.js" ]] || { echo "Wave 39 audit: inbox.js missing" >&2; exit 3; }
/usr/bin/grep -q 'from binario_marketing.service_wave39_app import serve' "$RES/launch.py" || { echo "Wave 39 audit: launch bootstrap is not using Wave 39" >&2; exit 3; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/binario-wave39-audit.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

"$PY" -I -B - "$RES/source/src" "$RES/source" "$TMP" <<'PY'
import sys
from pathlib import Path
from unittest.mock import patch

src = Path(sys.argv[1])
root = Path(sys.argv[2])
tmp = Path(sys.argv[3])
sys.path.insert(0, str(src))

from binario_marketing.meta_credentials import CredentialStatus
from binario_marketing.service_wave39_app import AppRuntime

runtime = AppRuntime.create(root, tmp / "data")
company = runtime.create_company({"name": "Wave 39 Inbox Audit"})
with patch(
    "binario_marketing.service_wave39_app.MetaCredentialStore.status",
    return_value=CredentialStatus(False, "none", False),
), patch(
    "binario_marketing.service_wave39_app.MetaInboxReader.from_env",
    side_effect=AssertionError("Wave 39 Full Mac audit must not create a Meta network client"),
):
    inbox = runtime.social_inbox(company["id"])

assert inbox["schema"] == "binario.marketing.social-inbox.v1", inbox
assert inbox["company_id"] == company["id"], inbox
assert inbox["configured"] is False, inbox
assert inbox["conversations"] == [], inbox
assert inbox["comments"] == [], inbox
assert inbox["summary"] == {"conversations": 0, "comments": 0, "crm_matches": 0}, inbox
assert runtime.social.list(company["id"]) == [], runtime.social.list(company["id"])
assert runtime.contacts_payload(company["id"]) == [], runtime.contacts_payload(company["id"])

if runtime.social_scheduler is not None:
    runtime.social_scheduler.shutdown()
runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
print("WAVE 39 FULL MAC INBOX AUDIT PASS")
PY
