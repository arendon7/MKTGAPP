#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH="arm64"
OUT="$ROOT/dist"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$ARCH" == "arm64" ]] || { echo "Wave 48 iteration builder is arm64-only" >&2; exit 4; }
"$ROOT/scripts/build_full_mac_wave47.sh" --arch "$ARCH" --out "$OUT"
APP="$OUT/Binario Marketing IA.app"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$LAUNCH" && -x "$PYTHON" ]] || { echo "Wave 48 launch/runtime missing" >&2; exit 4; }
"$PYTHON" -I -B - "$LAUNCH" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding='utf-8')
needle='from binario_marketing.service_wave47_app import serve\n'
if needle not in text:
    raise SystemExit('Wave 48 build blocked: Wave 47 entrypoint marker missing')
text=text.replace(needle, needle+'from binario_marketing.service_wave48_app import serve\n', 1)
path.write_text(text, encoding='utf-8')
PY
IDENTITY="${BINARIO_CODESIGN_IDENTITY:--}"
/usr/bin/codesign --force --deep --sign "$IDENTITY" "$APP"
/bin/bash "$ROOT/scripts/audit_wave48_paid_media_center.sh" "$APP"
printf 'WAVE 48 ARM64 ITERATION BUILD PASS: %s\n' "$APP"
