#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 <app>" >&2; exit 2; }
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
SERVICE="$SRC/src/binario_marketing/service_wave70_app.py"
UI="$SRC/web/release-evidence.js"
[[ -f "$SERVICE" && -f "$UI" && -f "$LAUNCH" ]] || { echo "W70 files missing" >&2; exit 4; }
/usr/bin/grep -q 'service_wave70_app import serve' "$LAUNCH"
/usr/bin/grep -q 'binario.marketing.release-evidence.v1' "$SERVICE"
/usr/bin/grep -q 'accepted_for_current_build' "$SERVICE"
/usr/bin/grep -q 'evidence_digest_mismatch' "$SERVICE"
/usr/bin/grep -q 'git_sha_mismatch' "$SERVICE"
/usr/bin/grep -q 'physical_uat_can_remove_only_uat_blocker' "$SERVICE"
/usr/bin/grep -q 'release_state_mutation_performed.*False' "$SERVICE"
/usr/bin/grep -q 'Puente UAT física → gate de release' "$UI"
/usr/bin/grep -q 'Revalidar evidencia' "$UI"
if /usr/bin/grep -Eq "method:[[:space:]]*['\"](POST|PATCH|PUT|DELETE)['\"]|setInterval|sendBeacon|supabase|vercel" "$UI"; then
  echo "W70 browser surface contains forbidden mutation/polling/cloud marker" >&2
  exit 5
fi
printf 'WAVE 70 RELEASE EVIDENCE AUDIT PASS\n'
