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
[[ "$ARCH" == "arm64" ]] || { echo "Current iteration builder is arm64-only" >&2; exit 4; }
"$ROOT/scripts/build_full_mac_app.sh" --arch "$ARCH" --out "$OUT"
APP="$OUT/Binario Marketing IA.app"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$LAUNCH" && -x "$PYTHON" ]] || { echo "Current launch/runtime missing" >&2; exit 4; }
"$PYTHON" -I -B - "$LAUNCH" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding='utf-8')
anchor='from binario_marketing.service_wave45_app import serve\n'
if anchor not in text:
    raise SystemExit('Current build blocked: Wave 45 entrypoint marker missing')
for module in ('service_wave47_app','service_wave48_app','service_wave49_app','service_wave50_app','service_wave51_app','service_wave52_app','service_wave53_app','service_wave54_app','service_wave55_app'):
    line=f'from binario_marketing.{module} import serve\n'
    if line not in text:
        text=text.replace(anchor, anchor+line, 1)
    anchor=line
path.write_text(text, encoding='utf-8')
PY
IDENTITY="${BINARIO_CODESIGN_IDENTITY:--}"
/usr/bin/codesign --force --deep --sign "$IDENTITY" "$APP"
/bin/bash "$ROOT/scripts/audit_wave47_product_surface.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave48_paid_media_center.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave49_creative_studio.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave50_command_center.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave51_ai_copilot.sh" "$APP"
# Wave 52 remains an explicit audited prerequisite for every later arm64 iteration.
/bin/bash "$ROOT/scripts/audit_wave52_learning_loop.sh" "$APP"
# Wave 53 Attribution Foundation remains an explicit audited prerequisite.
/bin/bash "$ROOT/scripts/audit_wave53_attribution_foundation.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave54_capture_bridge.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave55_lead_intake.sh" "$APP"
printf 'CURRENT ARM64 ITERATION BUILD PASS: Wave 55 · %s\n' "$APP"
