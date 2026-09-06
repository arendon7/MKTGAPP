#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist-post-w99"
ARCH="arm64"
APP_NAME="Binario Marketing IA Post-W99 Dev.app"
BASE_NAME="Binario Marketing IA.app"
CODESIGN_IDENTITY="${BINARIO_CODESIGN_IDENTITY:--}"

fail(){ printf 'POST-W99 DEV MAC BUILD BLOCKED: %s\n' "$1" >&2; exit 4; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --arch) ARCH="$2"; shift 2 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
[[ "$(uname -s)" == "Darwin" ]] || fail "build must run on macOS"
case "$ARCH" in arm64|aarch64) ARCH="arm64" ;; x86_64|amd64) ARCH="x86_64" ;; *) fail "unsupported architecture: $ARCH" ;; esac

TMP="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/binario-post-w99-dev.XXXXXX")"
cleanup(){ /bin/rm -rf "$TMP"; }
trap cleanup EXIT

mkdir -p "$OUT"
"$ROOT/scripts/build_full_mac_app.sh" --arch "$ARCH" --out "$TMP/base"
BASE="$TMP/base/$BASE_NAME"
[[ -d "$BASE" ]] || fail "base development bundle was not produced"
APP="$OUT/$APP_NAME"
/bin/rm -rf "$APP"
/usr/bin/ditto "$BASE" "$APP"

CONTENTS="$APP/Contents"
RESOURCES="$CONTENTS/Resources"
MACOS="$CONTENTS/MacOS"
LAUNCH="$RESOURCES/launch.py"
PYTHON="$RESOURCES/runtime/python/bin/python3"
PLIST="$CONTENTS/Info.plist"
[[ -x "$PYTHON" && -f "$LAUNCH" && -f "$PLIST" ]] || fail "copied bundle is incomplete"
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_dev_app.py" ]] || fail "post-W99 dev terminal is missing from packaged source"
[[ -f "$RESOURCES/source/src/binario_marketing/social_background.py" ]] || fail "post-W99 background worker is missing from packaged source"
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_today_portfolio_app.py" ]] || fail "post-W99 Today portfolio terminal is missing from packaged source"
[[ -f "$RESOURCES/source/src/binario_marketing/cloud_social_bridge.py" ]] || fail "post-W99 cloud social bridge core is missing from packaged source"
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_cloud_social_bridge_app.py" ]] || fail "post-W99 cloud social bridge terminal is missing from packaged source"
[[ -f "$RESOURCES/source/web/social-background-control.js" ]] || fail "post-W99 calendar control is missing from packaged source"
[[ -f "$RESOURCES/source/web/today-portfolio.js" ]] || fail "post-W99 Today portfolio browser surface is missing from packaged source"
[[ -f "$RESOURCES/source/web/cloud-social-bridge.js" ]] || fail "post-W99 cloud social browser control is missing from packaged source"

cat > "$LAUNCH" <<'PY'
from __future__ import annotations
import os
import sys
from pathlib import Path
resources = Path(__file__).resolve().parent
sys.path.insert(0, str(resources / "source" / "src"))
os.environ.setdefault("BINARIO_FFMPEG", str(resources / "runtime" / "media" / "bin" / "ffmpeg"))
os.environ.setdefault("BINARIO_FFPROBE", str(resources / "runtime" / "media" / "bin" / "ffprobe"))
os.environ.setdefault("BINARIO_WHISPER_CLI", str(resources / "runtime" / "transcription" / "bin" / "whisper-cli"))
os.environ.setdefault("BINARIO_WHISPER_MODEL", str(resources / "runtime" / "transcription" / "models" / "ggml-tiny.bin"))
from binario_marketing.service_post_w99_dev_app import serve
port = int(os.environ.get("BINARIO_PORT", "0"))
open_browser = os.environ.get("BINARIO_NO_BROWSER") != "1"
serve("127.0.0.1", port, open_browser=open_browser)
PY

/usr/libexec/PlistBuddy -c "Set :CFBundleDisplayName Binario Marketing IA Post-W99 Dev" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName Binario Marketing IA Post-W99 Dev" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier com.sistemabinario.marketing.postw99dev" "$PLIST"
/usr/bin/plutil -lint "$PLIST" >/dev/null

GIT_SHA="$(/usr/bin/git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf 'UNKNOWN')"
cat > "$RESOURCES/POST_W99_DEV_BUILD.json" <<JSON
{
  "schema": "binario.marketing.post-w99-dev-build.v1",
  "git_sha": "$GIT_SHA",
  "architecture": "$ARCH",
  "app_name": "$APP_NAME",
  "bundle_identifier": "com.sistemabinario.marketing.postw99dev",
  "terminal": "binario_marketing.service_post_w99_dev_app",
  "canonical_w99_main": "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",
  "release_authority": false,
  "physical_uat_authority": false,
  "w100": false
}
JSON

[[ -x "$MACOS/Binario Marketing IA" ]] || fail "native launcher is unavailable"
/usr/bin/codesign --force --deep --sign "$CODESIGN_IDENTITY" "$APP"
/usr/bin/codesign --verify --deep --strict "$APP"

printf 'POST-W99 DEV MAC BUILD PASS: %s (%s)\n' "$APP" "$ARCH"