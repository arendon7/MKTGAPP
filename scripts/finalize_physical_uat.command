#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
fail(){ printf 'COMBINED PHYSICAL UAT BLOCKED: %s\n' "$1" >&2; exit 4; }

[[ "$(uname -s)" == "Darwin" ]] || fail "finalization must run on macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "finalization requires the Apple Silicon physical-UAT host"
[[ "${GITHUB_ACTIONS:-}" != "true" && "${CI:-}" != "true" ]] || fail "physical UAT cannot be finalized in CI"

APP="$ROOT/PHYSICAL_UAT_WORK/Binario Marketing IA.app"
PY="$APP/Contents/Resources/runtime/python/bin/python3"
FINALIZER="$ROOT/FINALIZE_PHYSICAL_UAT.py"
VERIFY="$ROOT/PHYSICAL_UAT_HANDOFF_VERIFY.py"
PHASE_B="$ROOT/PHYSICAL_UAT_EVIDENCE/release-uat-evidence.json"
VERIFY_REPORT="$ROOT/PHYSICAL_UAT_EVIDENCE/PHYSICAL_UAT_HANDOFF_VERIFICATION.json"
OUT="$ROOT/PHYSICAL_UAT_EVIDENCE/combined"

[[ -d "$APP" ]] || fail "candidate app not found; run START_PHYSICAL_UAT.command first"
[[ -x "$PY" ]] || fail "embedded Python runtime missing"
[[ -f "$FINALIZER" ]] || fail "combined-UAT finalizer missing"
[[ -f "$VERIFY" ]] || fail "handoff verifier missing"
[[ -f "$PHASE_B" ]] || fail "Phase B evidence missing; complete RECORD_RELEASE_UAT.command first"

PHASE_A="${1:-}"
if [[ -z "$PHASE_A" ]]; then
  PHASE_A="$(/usr/bin/osascript <<'APPLESCRIPT'
try
  set chosenFile to choose file with prompt "Seleccione el JSON de evidencia Fase A descargado desde Release Evidence"
  return POSIX path of chosenFile
on error number -128
  return ""
end try
APPLESCRIPT
)"
fi
[[ -n "$PHASE_A" && -f "$PHASE_A" ]] || fail "Phase A evidence JSON was not selected"

# W97 closes the post-START integrity window: immediately before sealing the
# combined attestation, revalidate both the bundle signature and the exact
# extracted src/web/apps digest through the canonical handoff verifier.
/usr/bin/codesign --verify --deep --strict "$APP" || fail "candidate bundle signature drift detected"
"$PY" -I -B "$VERIFY" --delivery-dir "$ROOT" --app "$APP" --require-physical-host > "$VERIFY_REPORT"

mkdir -p "$OUT"
"$PY" -I -B "$FINALIZER" \
  --app "$APP" \
  --phase-a "$PHASE_A" \
  --phase-b "$PHASE_B" \
  --output "$OUT"

printf '\nCOMBINED PHYSICAL UAT ATTESTATION CREATED\n'
printf 'JSON: %s\n' "$OUT/combined-physical-uat-attestation.json"
printf 'Summary: %s\n' "$OUT/combined-physical-uat-attestation.md"
printf 'Final handoff verification: %s\n' "$VERIFY_REPORT"
printf '\nThis does not create a tag, sign, notarize, or publish a release.\n'
/usr/bin/open "$OUT"
