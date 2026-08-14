#!/bin/bash
set -euo pipefail
APP="${1:-}"
ARCH="${2:-}"
ROOT="${3:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "missing app bundle" >&2; exit 2; }
[[ "$ARCH" == "arm64" || "$ARCH" == "x86_64" ]] || { echo "invalid architecture" >&2; exit 2; }
[[ -n "$ROOT" && -d "$ROOT" ]] || { echo "missing repository root" >&2; exit 2; }
SRC="$ROOT/native/main_launcher.c"
OUT="$APP/Contents/MacOS/Binario Marketing IA"
[[ -f "$SRC" ]] || { echo "native launcher source missing" >&2; exit 3; }
/usr/bin/xcrun --sdk macosx clang -O2 -Wall -Wextra -target "$ARCH-apple-macos12.0" "$SRC" -o "$OUT"
chmod 755 "$OUT"
ARCHS="$(/usr/bin/lipo -archs "$OUT")"
[[ " $ARCHS " == *" $ARCH "* ]] || { echo "native launcher architecture mismatch: $ARCHS" >&2; exit 3; }
/usr/bin/file "$OUT" | /usr/bin/grep -q 'Mach-O' || { echo "main launcher is not Mach-O" >&2; exit 3; }
printf 'NATIVE MAIN LAUNCHER PASS: %s\n' "$ARCH"