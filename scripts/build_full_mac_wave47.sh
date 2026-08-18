#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Compatibility shim retained because the arm64 workflow and historical contracts
# still invoke this path. The canonical iteration logic now lives in
# build_full_mac_current.sh and includes service_wave47_app plus the latest service.
exec /bin/bash "$ROOT/scripts/build_full_mac_current.sh" "$@"
