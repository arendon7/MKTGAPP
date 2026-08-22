#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH=""
OUT="$ROOT/dist"
DISTRIBUTION="0"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    --distribution) DISTRIBUTION="1"; shift ;;
    *) echo "RELEASE CANDIDATE BUILD BLOCKED: unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -n "$ARCH" ]] || ARCH="$(uname -m)"
case "$ARCH" in
  arm64|aarch64) ARCH="arm64" ;;
  x86_64|amd64) ARCH="x86_64" ;;
  *) echo "RELEASE CANDIDATE BUILD BLOCKED: unsupported architecture: $ARCH" >&2; exit 4 ;;
esac

if [[ "$DISTRIBUTION" == "1" ]]; then
  [[ "${GITHUB_EVENT_NAME:-}" == "push" && "${GITHUB_REF:-}" == refs/tags/v* ]] || {
    echo "RELEASE CANDIDATE BUILD BLOCKED: --distribution requires a tag push origin" >&2
    exit 4
  }
  IDENTITY="${BINARIO_CODESIGN_IDENTITY:-}"
  [[ "$IDENTITY" == Developer\ ID\ Application:* ]] || {
    echo "RELEASE CANDIDATE BUILD BLOCKED: --distribution requires Developer ID Application identity" >&2
    exit 4
  }
  case "$ARCH" in
    arm64)
      # Distribution rebuild deliberately skips the physical-candidate writer.
      /bin/bash "$ROOT/scripts/build_full_mac_current.sh" --arch arm64 --out "$OUT"
      /bin/bash "$ROOT/scripts/audit_wave78_release_contract_drift_guard.sh" "$OUT/Binario Marketing IA.app"
      /bin/bash "$ROOT/scripts/audit_wave79_release_pipeline_parity.sh"
      ;;
    x86_64)
      /bin/bash "$ROOT/scripts/build_full_mac_current_x86_64.sh" --arch x86_64 --out "$OUT"
      ;;
  esac
else
  case "$ARCH" in
    arm64)
      /bin/bash "$ROOT/scripts/build_full_mac_current_guarded.sh" --arch arm64 --out "$OUT"
      ;;
    x86_64)
      /bin/bash "$ROOT/scripts/build_full_mac_current_x86_64.sh" --arch x86_64 --out "$OUT"
      ;;
  esac
fi

APP="$OUT/Binario Marketing IA.app"
RES="$APP/Contents/Resources"
LAUNCH="$RES/launch.py"
PY="$RES/runtime/python/bin/python3"
[[ -f "$LAUNCH" && -x "$PY" ]] || { echo "RELEASE CANDIDATE BUILD BLOCKED: launch/runtime missing" >&2; exit 4; }
/usr/bin/grep -q 'service_wave76_app import serve' "$LAUNCH" || {
  echo "RELEASE CANDIDATE BUILD BLOCKED: packaged runtime is not W76; refusing historical fallback" >&2
  exit 4
}

if [[ "$DISTRIBUTION" == "1" ]]; then
  [[ ! -e "$RES/PHYSICAL_UAT_CANDIDATE.json" && ! -e "$RES/PHYSICAL_UAT_CANDIDATE.md" ]] || {
    echo "RELEASE CANDIDATE BUILD BLOCKED: distribution rebuild contains physical-UAT candidate identity" >&2
    exit 4
  }
  "$PY" -I -B "$ROOT/scripts/write_distribution_rebuild_manifest.py" --app "$APP"
  /usr/bin/codesign --force --deep --options runtime --timestamp --sign "$BINARIO_CODESIGN_IDENTITY" "$APP"
  /usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
  "$PY" -I -B "$ROOT/scripts/write_distribution_rebuild_manifest.py" --app "$APP" --verify >/dev/null
  printf 'RELEASE DISTRIBUTION REBUILD PASS: W76 · %s · %s\n' "$ARCH" "$APP"
else
  printf 'RELEASE CANDIDATE CURRENT RUNTIME PASS: W76 · %s · %s\n' "$ARCH" "$APP"
fi
