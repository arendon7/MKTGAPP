#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --arch)
      [[ "$2" == "x86_64" || "$2" == "amd64" ]] || { echo "Current x86_64 builder only accepts x86_64" >&2; exit 4; }
      shift 2
      ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$(uname -s)" == "Darwin" ]] || { echo "Current x86_64 builder requires macOS" >&2; exit 4; }
[[ "$(uname -m)" == "x86_64" ]] || { echo "Current x86_64 builder requires a native Intel runner" >&2; exit 4; }

SOURCE="$ROOT/scripts/build_full_mac_current.sh"
TMP="$ROOT/scripts/.build_full_mac_current_x86_64.$$.sh"
cleanup(){ rm -f "$TMP"; }
trap cleanup EXIT
PYTHON_BIN="${PYTHON:-python3}"
"$PYTHON_BIN" - "$SOURCE" "$TMP" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1])
target = Path(sys.argv[2])
text = source.read_text(encoding="utf-8")
old = '[[ "$ARCH" == "arm64" ]] || { echo "Current iteration builder is arm64-only" >&2; exit 4; }'
new = '[[ "$ARCH" == "x86_64" ]] || { echo "Current iteration builder replay is x86_64-only" >&2; exit 4; }'
if text.count(old) != 1:
    raise SystemExit("W80 blocked: canonical current-builder architecture guard drifted; refusing historical fallback")
target.write_text(text.replace(old, new, 1), encoding="utf-8")
PY

/bin/bash "$TMP" --arch x86_64 --out "$OUT"
APP="$OUT/Binario Marketing IA.app"
LAUNCH="$APP/Contents/Resources/launch.py"
[[ -f "$LAUNCH" ]] || { echo "W80 blocked: x86_64 launch.py missing" >&2; exit 4; }
/usr/bin/grep -q 'service_wave76_app import serve' "$LAUNCH" || {
  echo "W80 blocked: x86_64 current runtime is not W76; refusing historical fallback" >&2
  exit 4
}
/bin/bash "$ROOT/scripts/audit_wave78_release_contract_drift_guard.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave79_release_pipeline_parity.sh"
/bin/bash "$ROOT/scripts/audit_wave80_x86_runtime_parity.sh" "$APP"
printf 'CURRENT X86_64 CERTIFICATION PASS: W76 + W78/W79/W80 guards · %s\n' "$APP"
