#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Compatibility shim retained because the arm64 workflow and historical contracts
# still invoke this path. The canonical runtime iteration logic remains in
# build_full_mac_current.sh; Wave 78 adds a post-build certification guard without
# changing the current W76 product runtime.
exec /bin/bash "$ROOT/scripts/build_full_mac_current_guarded.sh" "$@"
