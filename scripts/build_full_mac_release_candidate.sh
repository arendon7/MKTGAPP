#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH=""
OUT="$ROOT/dist"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "RELEASE CANDIDATE BUILD BLOCKED: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$ARCH" ]] || ARCH="$(uname -m)"
case "$ARCH" in
  arm64|aarch64) ARCH="arm64" ;;
  x86_64|amd64) ARCH="x86_64" ;;
  *) echo "RELEASE CANDIDATE BUILD BLOCKED: unsupported architecture: $ARCH" >&2; exit 4 ;;
esac

if [[ "$ARCH" != "arm64" ]]; then
  echo "RELEASE CANDIDATE BUILD BLOCKED: current W76 runtime + W78 certification chain is not yet certified for x86_64; refusing to fall back to the historical W45 base builder" >&2
  exit 4
fi

/bin/bash "$ROOT/scripts/build_full_mac_current_guarded.sh" --arch "$ARCH" --out "$OUT"
APP="$OUT/Binario Marketing IA.app"
LAUNCH="$APP/Contents/Resources/launch.py"
[[ -f "$LAUNCH" ]] || { echo "RELEASE CANDIDATE BUILD BLOCKED: launch.py missing" >&2; exit 4; }
/usr/bin/grep -q 'service_wave76_app import serve' "$LAUNCH" || {
  echo "RELEASE CANDIDATE BUILD BLOCKED: packaged runtime is not W76" >&2
  exit 4
}
printf 'RELEASE CANDIDATE CURRENT RUNTIME PASS: W76 + W78 guard · %s · %s\n' "$ARCH" "$APP"
