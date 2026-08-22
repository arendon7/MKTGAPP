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

case "$ARCH" in
  arm64)
    /bin/bash "$ROOT/scripts/build_full_mac_current_guarded.sh" --arch arm64 --out "$OUT"
    ;;
  x86_64)
    /bin/bash "$ROOT/scripts/build_full_mac_current_x86_64.sh" --arch x86_64 --out "$OUT"
    ;;
esac

APP="$OUT/Binario Marketing IA.app"
LAUNCH="$APP/Contents/Resources/launch.py"
[[ -f "$LAUNCH" ]] || { echo "RELEASE CANDIDATE BUILD BLOCKED: launch.py missing" >&2; exit 4; }
/usr/bin/grep -q 'service_wave76_app import serve' "$LAUNCH" || {
  echo "RELEASE CANDIDATE BUILD BLOCKED: packaged runtime is not W76; refusing historical fallback" >&2
  exit 4
}
printf 'RELEASE CANDIDATE CURRENT RUNTIME PASS: W76 · %s · %s\n' "$ARCH" "$APP"
