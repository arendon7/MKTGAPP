#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
fail(){ printf 'PRODUCT UAT EXPORT BLOCKED: %s\n' "$1" >&2; exit 4; }

[[ "$(uname -s)" == "Darwin" ]] || fail "this command must run on macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "physical product UAT requires Apple Silicon arm64"
[[ "${GITHUB_ACTIONS:-}" != "true" && "${CI:-}" != "true" ]] || fail "physical product UAT cannot be exported in CI"

APP="$ROOT/PHYSICAL_UAT_WORK/Binario Marketing IA.app"
PY="$APP/Contents/Resources/runtime/python/bin/python3"
VERIFY="$ROOT/PHYSICAL_UAT_HANDOFF_VERIFY.py"
COLLECT="$ROOT/PRODUCT_UAT_COLLECT.py"
[[ -d "$APP" ]] || fail "run START_PHYSICAL_UAT.command first; extracted app not found"
[[ -x "$PY" ]] || fail "embedded Python runtime missing"
[[ -f "$VERIFY" ]] || fail "handoff verifier missing"
[[ -f "$COLLECT" ]] || fail "product UAT collector missing"

"$PY" -I -B "$VERIFY" --delivery-dir "$ROOT" --app "$APP" --require-physical-host >/dev/null

printf 'Ruta completa del archivo de sesión Phase A (uat_*.json): '
IFS= read -r SESSION
SESSION="${SESSION/#\~/$HOME}"
[[ -f "$SESSION" ]] || fail "session file not found: $SESSION"

EVIDENCE_DIR="$ROOT/PHYSICAL_UAT_EVIDENCE"
OUTPUT="$EVIDENCE_DIR/product-uat-evidence.json"
mkdir -p "$EVIDENCE_DIR"
"$PY" -I -B "$COLLECT" --app "$APP" --session "$SESSION" --output "$OUTPUT"

printf '\nPHASE A EVIDENCE EXPORTED\n%s\n' "$OUTPUT"
printf 'This does not grant release authority. Phase B must also PASS on the same candidate.\n'
