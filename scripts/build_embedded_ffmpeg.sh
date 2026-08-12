#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIN_FILE="$ROOT/scripts/full_mac_media_runtime.env"
TARGET=""
REQUESTED_ARCH=""
CACHE_DIR="${FULL_MAC_FFMPEG_CACHE_DIR:-}"

fail(){ printf 'FULL MAC MEDIA BUILD BLOCKED: %s\n' "$1" >&2; exit 6; }
pass(){ printf 'PASS: %s\n' "$1"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) [[ $# -ge 2 ]] || fail "--target requires a directory"; TARGET="$2"; shift 2 ;;
    --arch) [[ $# -ge 2 ]] || fail "--arch requires arm64 or x86_64"; REQUESTED_ARCH="$2"; shift 2 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$(uname -s)" == "Darwin" ]] || fail "embedded FFmpeg must be built on macOS"
[[ -f "$PIN_FILE" ]] || fail "media pin file missing: $PIN_FILE"
[[ -n "$TARGET" ]] || fail "--target is required"
# shellcheck disable=SC1090
source "$PIN_FILE"

normalize_arch(){
  case "$1" in
    arm64|aarch64) printf 'arm64\n' ;;
    x86_64|amd64) printf 'x86_64\n' ;;
    *) return 1 ;;
  esac
}
HOST_ARCH="$(normalize_arch "$(uname -m)")" || fail "unsupported host architecture: $(uname -m)"
if [[ -n "$REQUESTED_ARCH" ]]; then ARCH="$(normalize_arch "$REQUESTED_ARCH")" || fail "unsupported requested architecture: $REQUESTED_ARCH"; else ARCH="$HOST_ARCH"; fi
[[ "$ARCH" == "$HOST_ARCH" ]] || fail "cross-architecture FFmpeg build is forbidden; requested $ARCH on $HOST_ARCH"

validate_runtime(){
  local dir="$1"
  [[ -x "$dir/bin/ffmpeg" && -x "$dir/bin/ffprobe" ]] || return 1
  [[ -f "$dir/FULL_MAC_MEDIA_RUNTIME.json" ]] || return 1
  /usr/bin/grep -q "\"source_commit\": \"$FULL_MAC_FFMPEG_COMMIT_SHA\"" "$dir/FULL_MAC_MEDIA_RUNTIME.json" || return 1
  /usr/bin/grep -q "\"architecture\": \"$ARCH\"" "$dir/FULL_MAC_MEDIA_RUNTIME.json" || return 1
  "$dir/bin/ffmpeg" -hide_banner -version >/dev/null 2>&1 || return 1
  "$dir/bin/ffprobe" -hide_banner -version >/dev/null 2>&1 || return 1
  return 0
}

if [[ -n "$CACHE_DIR" && -d "$CACHE_DIR" ]] && validate_runtime "$CACHE_DIR"; then
  rm -rf "$TARGET"
  mkdir -p "$(dirname "$TARGET")"
  /usr/bin/ditto "$CACHE_DIR" "$TARGET"
  pass "reused verified FFmpeg cache ($ARCH / $FULL_MAC_FFMPEG_VERSION)"
  exit 0
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/binario-ffmpeg.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
SRC="$TMP/src"
INSTALL="$TMP/install"
mkdir -p "$SRC" "$INSTALL"

/usr/bin/git -C "$SRC" init -q
/usr/bin/git -C "$SRC" remote add origin "$FULL_MAC_FFMPEG_REPOSITORY"
/usr/bin/git -C "$SRC" fetch --depth 1 origin "$FULL_MAC_FFMPEG_COMMIT_SHA"
/usr/bin/git -C "$SRC" checkout --detach -q FETCH_HEAD
ACTUAL_COMMIT="$(/usr/bin/git -C "$SRC" rev-parse HEAD)"
[[ "$ACTUAL_COMMIT" == "$FULL_MAC_FFMPEG_COMMIT_SHA" ]] || fail "FFmpeg source commit mismatch: $ACTUAL_COMMIT"
pass "FFmpeg source commit verified: $ACTUAL_COMMIT"

CONFIG_FLAGS=(
  "--prefix=$INSTALL"
  "--disable-doc"
  "--disable-debug"
  "--disable-ffplay"
  "--disable-network"
  "--disable-autodetect"
  "--enable-videotoolbox"
  "--enable-audiotoolbox"
  "--enable-small"
)
if [[ "$ARCH" == "x86_64" ]]; then CONFIG_FLAGS+=("--disable-x86asm"); fi

(
  cd "$SRC"
  ./configure "${CONFIG_FLAGS[@]}"
  /usr/bin/make -j"$(/usr/sbin/sysctl -n hw.ncpu)"
)

rm -rf "$TARGET"
mkdir -p "$TARGET/bin" "$TARGET/licenses"
/bin/cp "$SRC/ffmpeg" "$TARGET/bin/ffmpeg"
/bin/cp "$SRC/ffprobe" "$TARGET/bin/ffprobe"
chmod +x "$TARGET/bin/ffmpeg" "$TARGET/bin/ffprobe"
for license in LICENSE.md COPYING.LGPLv2.1; do
  [[ -f "$SRC/$license" ]] && /bin/cp "$SRC/$license" "$TARGET/licenses/$license"
done

for binary in "$TARGET/bin/ffmpeg" "$TARGET/bin/ffprobe"; do
  /usr/bin/codesign --force --sign - "$binary" >/dev/null
  "$binary" -hide_banner -version >/dev/null
  DEPS="$(/usr/bin/otool -L "$binary")"
  if printf '%s\n' "$DEPS" | /usr/bin/grep -Eq '(/opt/homebrew|/usr/local|/private/tmp|/Users/runner)'; then
    printf '%s\n' "$DEPS" >&2
    fail "FFmpeg binary links to non-system build-host dependency"
  fi
done

"$TARGET/bin/ffmpeg" -hide_banner -encoders 2>/dev/null | /usr/bin/grep -q 'h264_videotoolbox' || fail "h264_videotoolbox encoder is missing"
SMOKE="$TMP/smoke.mp4"
"$TARGET/bin/ffmpeg" -hide_banner -loglevel error -f lavfi -i 'testsrc2=size=320x180:rate=10' -t 0.4 -c:v mpeg4 -an -y "$SMOKE"
"$TARGET/bin/ffprobe" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$SMOKE" | /usr/bin/grep -q '^320,180$' || fail "FFmpeg synthetic render/probe smoke failed"

cat > "$TARGET/FULL_MAC_MEDIA_RUNTIME.json" <<JSON
{
  "architecture": "$ARCH",
  "ffmpeg_version": "$FULL_MAC_FFMPEG_VERSION",
  "license_profile": "$FULL_MAC_FFMPEG_LICENSE_PROFILE",
  "repository": "$FULL_MAC_FFMPEG_REPOSITORY",
  "schema": "binario.marketing.full-mac-media-runtime.v1",
  "source_commit": "$FULL_MAC_FFMPEG_COMMIT_SHA",
  "source_tag": "$FULL_MAC_FFMPEG_TAG",
  "source_tag_object": "$FULL_MAC_FFMPEG_TAG_OBJECT_SHA"
}
JSON

validate_runtime "$TARGET" || fail "built media runtime failed final validation"
if [[ -n "$CACHE_DIR" ]]; then
  rm -rf "$CACHE_DIR"
  mkdir -p "$(dirname "$CACHE_DIR")"
  /usr/bin/ditto "$TARGET" "$CACHE_DIR"
fi
pass "embedded FFmpeg built and verified ($ARCH / $FULL_MAC_FFMPEG_VERSION)"
