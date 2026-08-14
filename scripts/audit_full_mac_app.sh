#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
MACOS="$APP/Contents/MacOS"
LAUNCHER="$MACOS/Binario Marketing IA"
KEYCHAIN_HELPER="$MACOS/binario-meta-keychain"
PY="$RES/runtime/python/bin/python3"
FFMPEG="$RES/runtime/media/bin/ffmpeg"
FFPROBE="$RES/runtime/media/bin/ffprobe"
PROVENANCE="$RES/BUILD_PROVENANCE.json"
[[ -x "$LAUNCHER" ]] || { echo "missing launcher" >&2; exit 3; }
[[ -x "$KEYCHAIN_HELPER" ]] || { echo "missing native Meta Keychain helper" >&2; exit 3; }
[[ -x "$PY" ]] || { echo "missing embedded python" >&2; exit 3; }
[[ -x "$FFMPEG" && -x "$FFPROBE" ]] || { echo "missing embedded media runtime" >&2; exit 3; }
[[ -f "$RES/runtime/media/FULL_MAC_MEDIA_RUNTIME.json" ]] || { echo "missing media provenance" >&2; exit 3; }
[[ -f "$PROVENANCE" ]] || { echo "missing build provenance" >&2; exit 3; }
[[ -f "$RES/source/web/index.html" ]] || { echo "missing web UI" >&2; exit 3; }
[[ -f "$RES/source/web/marketing-ops.js" && -f "$RES/source/web/marketing-ops.css" ]] || { echo "missing Wave 31 marketing operations UI" >&2; exit 3; }
[[ -f "$RES/source/web/crm.js" ]] || { echo "missing Wave 32 CRM UI" >&2; exit 3; }
[[ -f "$RES/source/src/binario_marketing/company_store.py" && -f "$RES/source/src/binario_marketing/service_wave31.py" ]] || { echo "missing Wave 31 company runtime" >&2; exit 3; }
[[ -f "$RES/source/src/binario_marketing/crm_store.py" && -f "$RES/source/src/binario_marketing/service_wave32.py" ]] || { echo "missing Wave 32 CRM runtime" >&2; exit 3; }
[[ -f "$RES/source/apps/editor-video/manifest.json" ]] || { echo "missing app manifests" >&2; exit 3; }
/usr/bin/grep -q 'from binario_marketing.service_wave32 import serve' "$RES/launch.py" || { echo "Mac launch bootstrap is not using Wave 32 runtime" >&2; exit 3; }
/usr/bin/plutil -lint "$APP/Contents/Info.plist" >/dev/null
/usr/bin/codesign --verify --deep --strict "$APP"

LAUNCHER_KIND="$(/usr/bin/file "$LAUNCHER")"
/usr/bin/grep -q 'Mach-O' <<<"$LAUNCHER_KIND" || { echo "main CFBundleExecutable is not Mach-O: $LAUNCHER_KIND" >&2; exit 3; }
HOST_ARCH="$(uname -m)"
LAUNCHER_ARCHS="$(/usr/bin/lipo -archs "$LAUNCHER")"
[[ " $LAUNCHER_ARCHS " == *" $HOST_ARCH "* ]] || { echo "main launcher architecture mismatch: host=$HOST_ARCH launcher=$LAUNCHER_ARCHS" >&2; exit 3; }
if /usr/bin/grep -Eq '(^|[;&|[:space:]])python3([[:space:]]|$)' "$LAUNCHER"; then echo "launcher contains host python invocation" >&2; exit 3; fi
/usr/bin/grep -q 'runtime/media/bin' "$LAUNCHER" || { echo "launcher does not prioritize embedded media runtime" >&2; exit 3; }
/usr/bin/grep -q 'BINARIO_META_KEYCHAIN_HELPER' "$LAUNCHER" || { echo "launcher does not expose bundled Meta Keychain helper" >&2; exit 3; }

TMP="$(mktemp -d "${TMPDIR:-/tmp}/binario-media-audit.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
LS_PROBE="$TMP/launchservices-probe.txt"
/usr/bin/open -n "$APP" --args --launchservices-probe "$LS_PROBE"
LS_READY=0
for _ in $(seq 1 40); do
  if [[ -f "$LS_PROBE" ]]; then LS_READY=1; break; fi
  sleep 0.25
done
[[ "$LS_READY" == "1" ]] || { echo "LaunchServices did not execute CFBundleExecutable" >&2; exit 3; }
/usr/bin/grep -q '^ok$' "$LS_PROBE" || { echo "LaunchServices probe result invalid" >&2; exit 3; }
echo "LAUNCHSERVICES APP BOOT PASS"

KEYCHAIN_STATUS="$(cd "$MACOS" && ./binario-meta-keychain status)" || { echo "native Meta Keychain helper cannot access Keychain" >&2; exit 3; }
[[ "$KEYCHAIN_STATUS" == "missing" || "$KEYCHAIN_STATUS" == "configured" ]] || { echo "unexpected Keychain helper status: $KEYCHAIN_STATUS" >&2; exit 3; }

for binary in "$FFMPEG" "$FFPROBE"; do
  OTOOL_OUTPUT="$(/usr/bin/otool -L "$binary")"
  LINKED_DEPS="${OTOOL_OUTPUT#*$'\n'}"
  if /usr/bin/grep -Eq '(/opt/homebrew|/usr/local|/private/tmp|/Users/runner)' <<<"$LINKED_DEPS"; then
    printf '%s\n' "$OTOOL_OUTPUT" >&2
    echo "media runtime has non-system dependency" >&2
    exit 3
  fi
done
ENCODERS_FILE="$TMP/encoders.txt"
"$FFMPEG" -hide_banner -encoders >"$ENCODERS_FILE" 2>&1
/usr/bin/grep -q 'h264_videotoolbox' "$ENCODERS_FILE" || { echo "h264_videotoolbox unavailable" >&2; exit 3; }
"$FFMPEG" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=320x180:rate=10' -t 0.4 -c:v mpeg4 -an -y "$TMP/smoke.mp4"
PROBE_DIMENSIONS="$("$FFPROBE" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$TMP/smoke.mp4")"
[[ "$PROBE_DIMENSIONS" == "320,180" ]] || { echo "unexpected synthetic probe dimensions: $PROBE_DIMENSIONS" >&2; exit 3; }

PLIST_SHORT="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist")"
PLIST_BUILD="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP/Contents/Info.plist")"

BINARIO_FFMPEG="$FFMPEG" BINARIO_FFPROBE="$FFPROBE" BINARIO_META_KEYCHAIN_HELPER="$KEYCHAIN_HELPER" "$PY" -I -B - "$RES/source/src" "$RES/source" "$PROVENANCE" "$PLIST_SHORT" "$PLIST_BUILD" "$TMP" <<'PY'
import json, sys
from pathlib import Path
src, root, provenance_path = map(Path, sys.argv[1:4])
plist_short, plist_build = sys.argv[4:6]
tmp = Path(sys.argv[6])
sys.path.insert(0, str(src))
from binario_marketing.hub import discover_apps
from binario_marketing.meta_credentials import MetaCredentialStore
from binario_marketing.service_wave32 import AppRuntime
from binario_marketing.version import MACOS_BUNDLE_VERSION, MACOS_SHORT_VERSION, __version__
from binario_marketing.video.render import media_runtime_status
apps = discover_apps(root)
assert len(apps) == 12, len(apps)
runtime = AppRuntime.create(root, tmp / 'binario-audit-data-wave32')
assert len(runtime.apps_payload()) == 12
assert runtime.companies_payload() == [], runtime.companies_payload()
assert runtime.crm_summary() == {
    'contacts': 0,
    'opportunities_open': 0,
    'opportunities_won': 0,
    'pending_activities': 0,
    'overdue_activities': 0,
    'stage_counts': {'NEW': 0, 'CONTACTED': 0, 'INTERESTED': 0, 'PROPOSAL': 0, 'WON': 0, 'LOST': 0},
    'next_activities': [],
}, runtime.crm_summary()
credential_status = MetaCredentialStore().status()
assert credential_status.writable is True, credential_status
status = media_runtime_status()
assert status['h264_videotoolbox'] is True, status
provenance = json.loads(provenance_path.read_text(encoding='utf-8'))
assert provenance['product_version'] == __version__, provenance
assert provenance['macos_short_version'] == MACOS_SHORT_VERSION, provenance
assert provenance['macos_bundle_version'] == MACOS_BUNDLE_VERSION, provenance
assert provenance['meta_keychain_helper'] == 'SecItem/data-protection-first', provenance
assert plist_short == MACOS_SHORT_VERSION, (plist_short, MACOS_SHORT_VERSION)
assert plist_build == MACOS_BUNDLE_VERSION, (plist_build, MACOS_BUNDLE_VERSION)
if runtime.social_scheduler is not None:
    runtime.social_scheduler.shutdown()
runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
print(json.dumps({'apps': len(apps), 'companies': 0, 'crm_contacts': 0, 'media': status, 'keychain': credential_status.source, 'version': __version__, 'status': 'PASS'}))
PY
printf 'FULL MAC AUDIT PASS: %s\n' "$APP"