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

# shellcheck disable=SC1091
source "$ROOT/scripts/full_mac_media_runtime.env"
APP="$OUT/$APP_NAME"
CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
PY_RUNTIME="$RESOURCES/runtime/python"
MEDIA_RUNTIME="$RESOURCES/runtime/media"
SOURCE="$RESOURCES/source"
rm -rf "$APP"
mkdir -p "$MACOS" "$RESOURCES" "$SOURCE"

"$ROOT/scripts/bootstrap_full_mac_python.sh" --target "$PY_RUNTIME" --arch "$ARCH"
"$ROOT/scripts/build_embedded_ffmpeg.sh" --target "$MEDIA_RUNTIME" --arch "$ARCH"
/usr/bin/ditto "$ROOT/src" "$SOURCE/src"
/usr/bin/ditto "$ROOT/apps" "$SOURCE/apps"
/usr/bin/ditto "$ROOT/web" "$SOURCE/web"
/bin/cp "$ROOT/pyproject.toml" "$SOURCE/pyproject.toml"

GIT_SHA="$(/usr/bin/git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf 'UNKNOWN')"
cat > "$RESOURCES/BUILD_PROVENANCE.json" <<JSON
{
  "schema": "binario.marketing.full-mac-build.v2",
  "git_sha": "$GIT_SHA",
  "architecture": "$ARCH",
  "app_name": "$APP_NAME",
  "embedded_python": "3.12.13",
  "embedded_ffmpeg": "$FULL_MAC_FFMPEG_VERSION",
  "ffmpeg_source_commit": "$FULL_MAC_FFMPEG_COMMIT_SHA"
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
from binario_marketing.service import serve
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
[[ -x "$PYTHON" ]] || { echo "BINARIO Marketing Python runtime missing" >&2; exit 5; }
[[ -x "$MEDIA_BIN/ffmpeg" && -x "$MEDIA_BIN/ffprobe" ]] || { echo "BINARIO Marketing media runtime missing" >&2; exit 5; }
export PATH="$MEDIA_BIN:$RESOURCES/runtime/python/bin:/usr/bin:/bin"
export BINARIO_FFMPEG="$MEDIA_BIN/ffmpeg"
export BINARIO_FFPROBE="$MEDIA_BIN/ffprobe"
unset PYTHONHOME PYTHONPATH
export PYTHONNOUSERSITE=1
export PYTHONDONTWRITEBYTECODE=1
exec "$PYTHON" -I -B "$RESOURCES/launch.py"
SH
chmod +x "$MACOS/Binario Marketing IA"

cat > "$CONTENTS/Info.plist" <<'PLIST'
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
<key>CFBundleShortVersionString</key><string>0.9.0</string>
<key>CFBundleVersion</key><string>2</string>
<key>LSMinimumSystemVersion</key><string>12.0</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST
/usr/bin/plutil -lint "$CONTENTS/Info.plist" >/dev/null
/usr/bin/codesign --force --deep --sign - "$APP"
printf 'FULL MAC BUILD PASS: %s\n' "$APP"
