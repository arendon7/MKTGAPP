#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP="${1:-$ROOT/dist/Binario Marketing IA.app}"
ARCH="${2:-$(uname -m)}"
PIN="$ROOT/scripts/full_mac_transcription_runtime.env"
[[ -f "$PIN" ]] || { echo "missing whisper pin" >&2; exit 2; }
# shellcheck disable=SC1090
source "$PIN"
RUNTIME="$APP/Contents/Resources/runtime/transcription"
CLI="$RUNTIME/bin/whisper-cli"
MODEL="$RUNTIME/models/$WHISPER_MODEL_NAME"
MANIFEST="$RUNTIME/RUNTIME.json"
[[ -x "$CLI" ]] || { echo "missing embedded whisper-cli: $CLI" >&2; exit 3; }
[[ -f "$MODEL" ]] || { echo "missing embedded whisper model: $MODEL" >&2; exit 3; }
[[ -f "$MANIFEST" ]] || { echo "missing whisper runtime manifest" >&2; exit 3; }

case "$ARCH" in
  arm64) file "$CLI" | grep -Eq 'arm64|Mach-O 64-bit executable arm64' ;;
  x86_64) file "$CLI" | grep -Eq 'x86_64|Mach-O 64-bit executable x86_64' ;;
  *) echo "unsupported architecture: $ARCH" >&2; exit 4 ;;
esac

MODEL_SHA="$(shasum -a 256 "$MODEL" | awk '{print $1}')"
[[ "$MODEL_SHA" == "$WHISPER_MODEL_SHA256" ]] || { echo "embedded model SHA mismatch: $MODEL_SHA" >&2; exit 5; }
MODEL_BYTES_ACTUAL="$(wc -c < "$MODEL" | tr -d ' ')"
[[ "$MODEL_BYTES_ACTUAL" == "$WHISPER_MODEL_BYTES" ]] || { echo "embedded model bytes mismatch" >&2; exit 5; }

python3 - "$MANIFEST" "$WHISPER_TAG" "$WHISPER_COMMIT" "$WHISPER_MODEL_NAME" "$WHISPER_MODEL_SHA256" "$ARCH" <<'PY'
import json,sys
row=json.load(open(sys.argv[1],encoding='utf-8'))
assert row['engine']=='whisper.cpp',row
assert row['whisper_tag']==sys.argv[2],row
assert row['whisper_commit']==sys.argv[3],row
assert row['model']==sys.argv[4],row
assert row['model_sha256']==sys.argv[5],row
assert row['architecture']==sys.argv[6],row
PY

LINKS="$(mktemp "${TMPDIR:-/tmp}/whisper-audit-links.XXXXXX")"
otool -L "$CLI" > "$LINKS"
if tail -n +2 "$LINKS" | grep -E '/opt/homebrew|/usr/local/(Cellar|opt|lib)'; then
  echo "embedded whisper-cli links against host package manager" >&2
  cat "$LINKS" >&2
  rm -f "$LINKS"
  exit 6
fi
rm -f "$LINKS"
"$CLI" --help >/dev/null 2>&1 || { echo "embedded whisper-cli help smoke failed" >&2; exit 7; }
echo "PASS: embedded whisper.cpp $WHISPER_TAG + $WHISPER_MODEL_NAME ($ARCH)"
