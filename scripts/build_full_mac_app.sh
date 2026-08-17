#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
ARCH=""
APP_NAME="Binario Marketing IA.app"

fail(){ printf 'FULL MAC BUILD BLOCKED: %s\n' "$1" >&2; exit 4; }
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --arch) ARCH="$2"; shift 2 ;;
    *) fail "unknown argument: $1" ;;
  esac
done
[[ "$(uname -s)" == "Darwin" ]] || fail "build must run on macOS"
[[ -n "$ARCH" ]] || ARCH="$(uname -m)"
case "$ARCH" in arm64|aarch64) ARCH="arm64" ;; x86_64|amd64) ARCH="x86_64" ;; *) fail "unsupported architecture: $ARCH" ;; esac

source "$ROOT/scripts/full_mac_media_runtime.env"
source "$ROOT/scripts/full_mac_transcription_runtime.env"
APP="$OUT/$APP_NAME"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
PY_RUNTIME="$RESOURCES/runtime/python"
MEDIA_RUNTIME="$RESOURCES/runtime/media"
TRANSCRIPTION_RUNTIME="$RESOURCES/runtime/transcription"
SOURCE="$RESOURCES/source"
KEYCHAIN_HELPER="$MACOS/binario-meta-keychain"
rm -rf "$APP"
mkdir -p "$MACOS" "$RESOURCES" "$SOURCE"

"$ROOT/scripts/bootstrap_full_mac_python.sh" --target "$PY_RUNTIME" --arch "$ARCH"
VERSION_FIELDS="$("$PY_RUNTIME/bin/python3" -I -B - "$ROOT/src" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from binario_marketing.version import MACOS_BUNDLE_VERSION, MACOS_SHORT_VERSION, __version__
print(f"{__version__}\t{MACOS_SHORT_VERSION}\t{MACOS_BUNDLE_VERSION}")
PY
)"
IFS=$'\t' read -r PRODUCT_VERSION MACOS_SHORT_VERSION MACOS_BUNDLE_VERSION <<< "$VERSION_FIELDS"
[[ -n "$PRODUCT_VERSION" ]] || fail "canonical product version is empty"
[[ "$MACOS_SHORT_VERSION" =~ ^[0-9]+(\.[0-9]+){1,2}$ ]] || fail "invalid macOS short version: $MACOS_SHORT_VERSION"
[[ "$MACOS_BUNDLE_VERSION" =~ ^[0-9]+(\.[0-9]+){0,2}$ ]] || fail "invalid macOS bundle version: $MACOS_BUNDLE_VERSION"

"$ROOT/scripts/build_embedded_ffmpeg.sh" --target "$MEDIA_RUNTIME" --arch "$ARCH"
"$ROOT/scripts/build_embedded_whisper.sh" --arch "$ARCH" --output "$TRANSCRIPTION_RUNTIME"
"$ROOT/scripts/audit_embedded_whisper.sh" "$APP" "$ARCH"
/usr/bin/ditto "$ROOT/src" "$SOURCE/src"
/usr/bin/ditto "$ROOT/apps" "$SOURCE/apps"
/usr/bin/ditto "$ROOT/web" "$SOURCE/web"
/bin/cp "$ROOT/pyproject.toml" "$SOURCE/pyproject.toml"

[[ -f "$ROOT/native/meta_keychain_helper.swift" ]] || fail "Meta Keychain helper source missing"
/usr/bin/xcrun --sdk macosx swiftc -O -target "$ARCH-apple-macos12.0" "$ROOT/native/meta_keychain_helper.swift" -framework Foundation -framework Security -o "$KEYCHAIN_HELPER"
[[ -x "$KEYCHAIN_HELPER" ]] || fail "Meta Keychain helper build failed"
HELPER_ARCHS="$(/usr/bin/lipo -archs "$KEYCHAIN_HELPER")"
[[ " $HELPER_ARCHS " == *" $ARCH "* ]] || fail "Meta Keychain helper architecture mismatch: $HELPER_ARCHS"

GIT_SHA="$(/usr/bin/git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf 'UNKNOWN')"
cat > "$RESOURCES/BUILD_PROVENANCE.json" <<JSON
{
  "schema": "binario.marketing.full-mac-build.v3",
  "git_sha": "$GIT_SHA",
  "architecture": "$ARCH",
  "app_name": "$APP_NAME",
  "product_version": "$PRODUCT_VERSION",
  "macos_short_version": "$MACOS_SHORT_VERSION",
  "macos_bundle_version": "$MACOS_BUNDLE_VERSION",
  "embedded_python": "3.12.13",
  "embedded_ffmpeg": "$FULL_MAC_FFMPEG_VERSION",
  "ffmpeg_source_commit": "$FULL_MAC_FFMPEG_COMMIT_SHA",
  "embedded_whisper": "$WHISPER_TAG",
  "whisper_source_commit": "$WHISPER_COMMIT",
  "whisper_model": "$WHISPER_MODEL_NAME",
  "whisper_model_sha256": "$WHISPER_MODEL_SHA256",
  "meta_keychain_helper": "SecItem/data-protection-first"
}
JSON

cat > "$RESOURCES/launch.py" <<'PY'
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
from binario_marketing.service_wave38_app import serve
from binario_marketing.service_wave39_app import serve
from binario_marketing.service_wave41_app import serve
port = int(os.environ.get("BINARIO_PORT", "0"))
open_browser = os.environ.get("BINARIO_NO_BROWSER") != "1"
serve("127.0.0.1", port, open_browser=open_browser)
PY

cat > "$MACOS/Binario Marketing IA" <<'SH'
#!/bin/bash
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
RESOURCES="$(cd "$HERE/../Resources" && pwd)"
PYTHON="$RESOURCES/runtime/python/bin/python3"
MEDIA_BIN="$RESOURCES/runtime/media/bin"
TRANSCRIPTION="$RESOURCES/runtime/transcription"
KEYCHAIN_HELPER="$HERE/binario-meta-keychain"
[[ -x "$PYTHON" ]] || { echo "BINARIO Marketing Python runtime missing" >&2; exit 5; }
[[ -x "$MEDIA_BIN/ffmpeg" && -x "$MEDIA_BIN/ffprobe" ]] || { echo "BINARIO Marketing media runtime missing" >&2; exit 5; }
[[ -x "$TRANSCRIPTION/bin/whisper-cli" && -f "$TRANSCRIPTION/models/ggml-tiny.bin" ]] || { echo "BINARIO Marketing transcription runtime missing" >&2; exit 5; }
[[ -x "$KEYCHAIN_HELPER" ]] || { echo "BINARIO Marketing Keychain helper missing" >&2; exit 5; }
export PATH="$MEDIA_BIN:$TRANSCRIPTION/bin:$RESOURCES/runtime/python/bin:/usr/bin:/bin"
export BINARIO_FFMPEG="$MEDIA_BIN/ffmpeg"
export BINARIO_FFPROBE="$MEDIA_BIN/ffprobe"
export BINARIO_WHISPER_CLI="$TRANSCRIPTION/bin/whisper-cli"
export BINARIO_WHISPER_MODEL="$TRANSCRIPTION/models/ggml-tiny.bin"
export BINARIO_META_KEYCHAIN_HELPER="$KEYCHAIN_HELPER"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" -I -B "$RESOURCES/launch.py"
SH
chmod +x "$MACOS/Binario Marketing IA"

cat > "$CONTENTS/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>es</string>
<key>CFBundleDisplayName</key><string>Binario Marketing IA</string>
<key>CFBundleExecutable</key><string>Binario Marketing IA</string>
<key>CFBundleIdentifier</key><string>com.sistemabinario.marketing</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleName</key><string>Binario Marketing IA</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>$MACOS_SHORT_VERSION</string>
<key>CFBundleVersion</key><string>$MACOS_BUNDLE_VERSION</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
/bin/bash "$ROOT/scripts/build_native_main_launcher.sh" "$APP" "$ARCH" "$ROOT"
/usr/bin/plutil -lint "$CONTENTS/Info.plist" >/dev/null
/usr/bin/codesign --force --deep --sign - "$APP"
/bin/bash "$ROOT/scripts/audit_wave39_inbox.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave40_crm_triage.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave41_manual_replies.sh" "$APP"
printf 'FULL MAC BUILD PASS: %s (%s / %s)\n' "$APP" "$PRODUCT_VERSION" "$ARCH"