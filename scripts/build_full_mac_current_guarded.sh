#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
ARGS=("$@")
for ((i=0; i<${#ARGS[@]}; i++)); do
  if [[ "${ARGS[$i]}" == "--out" ]]; then
    (( i + 1 < ${#ARGS[@]} )) || { echo "--out requires a value" >&2; exit 2; }
    OUT="${ARGS[$((i+1))]}"
  fi
done

/bin/bash "$ROOT/scripts/build_full_mac_current.sh" "${ARGS[@]}"
APP="$OUT/Binario Marketing IA.app"
/bin/bash "$ROOT/scripts/audit_wave78_release_contract_drift_guard.sh" "$APP"
printf 'CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 78 · %s\n' "$APP"
