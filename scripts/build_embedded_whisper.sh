#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIN="$ROOT/scripts/full_mac_transcription_runtime.env"
[[ -f "$PIN" ]] || { echo "missing transcription runtime pin: $PIN" >&2; exit 2; }
# shellcheck disable=SC1090
source "$PIN"

ARCH=""
OUTPUT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$ARCH" == "arm64" || "$ARCH" == "x86_64" ]] || { echo "--arch must be arm64 or x86_64" >&2; exit 2; }
[[ -n "$OUTPUT" ]] || { echo "--output is required" >&2; exit 2; }

NATIVE="$(uname -m)"
[[ "$NATIVE" == "$ARCH" ]] || { echo "native runner architecture $NATIVE does not match requested $ARCH" >&2; exit 3; }
command -v git >/dev/null
command -v cmake >/dev/null
command -v curl >/dev/null
command -v shasum >/dev/null
command -v otool >/dev/null
command -v file >/dev/null

CACHE="${FULL_MAC_WHISPER_CACHE_DIR:-$ROOT/.cache/full-mac-whisper-$ARCH}"
CACHE_BIN="$CACHE/bin/whisper-cli"
CACHE_MODEL="$CACHE/models/$WHISPER_MODEL_NAME"
CACHE_MANIFEST="$CACHE/RUNTIME.json"
VALID_CACHE=0
if [[ -x "$CACHE_BIN" && -f "$CACHE_MODEL" && -f "$CACHE_MANIFEST" ]]; then
  if python3 - "$CACHE_MANIFEST" "$WHISPER_COMMIT" "$WHISPER_MODEL_SHA256" "$ARCH" <<'PY'
import json,sys
row=json.load(open(sys.argv[1],encoding='utf-8'))
assert row['whisper_commit']==sys.argv[2]
assert row['model_sha256']==sys.argv[3]
assert row['architecture']==sys.argv[4]
PY
  then
    GOT="$(shasum -a 256 "$CACHE_MODEL" | awk '{print $1}')"
    [[ "$GOT" == "$WHISPER_MODEL_SHA256" ]] && VALID_CACHE=1
  fi
fi

if [[ "$VALID_CACHE" != "1" ]]; then
  rm -rf "$CACHE"
  mkdir -p "$CACHE/bin" "$CACHE/models" "$CACHE/licenses"
  WORK="$(mktemp -d "${TMPDIR:-/tmp}/binario-whisper.XXXXXX")"
  trap 'rm -rf "$WORK"' EXIT
  SRC="$WORK/whisper.cpp"
  git clone --quiet --no-checkout "$WHISPER_REPOSITORY" "$SRC"
  git -C "$SRC" fetch --quiet --depth 1 origin "$WHISPER_COMMIT"
  git -C "$SRC" checkout --quiet --detach "$WHISPER_COMMIT"
  ACTUAL="$(git -C "$SRC" rev-parse HEAD)"
  [[ "$ACTUAL" == "$WHISPER_COMMIT" ]] || { echo "whisper.cpp commit mismatch" >&2; exit 4; }

  BUILD="$WORK/build"
  cmake -S "$SRC" -B "$BUILD" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_SHARED_LIBS=OFF \
    -DWHISPER_BUILD_EXAMPLES=ON \
    -DWHISPER_BUILD_TESTS=OFF \
    -DWHISPER_BUILD_SERVER=OFF \
    -DGGML_NATIVE=OFF \
    -DGGML_METAL=OFF \
    -DGGML_ACCELERATE=ON
  cmake --build "$BUILD" --config Release --target whisper-cli --parallel "$(sysctl -n hw.logicalcpu 2>/dev/null || echo 4)"
  BUILT="$(find "$BUILD" -type f -name whisper-cli -perm -111 -print -quit)"
  [[ -n "$BUILT" && -x "$BUILT" ]] || { echo "whisper-cli binary was not produced" >&2; exit 5; }
  cp "$BUILT" "$CACHE_BIN"
  chmod 755 "$CACHE_BIN"
  [[ -f "$SRC/LICENSE" ]] && cp "$SRC/LICENSE" "$CACHE/licenses/whisper.cpp-LICENSE"

  curl --fail --location --retry 4 --retry-delay 2 "$WHISPER_MODEL_URL" -o "$CACHE_MODEL"
  GOT="$(shasum -a 256 "$CACHE_MODEL" | awk '{print $1}')"
  [[ "$GOT" == "$WHISPER_MODEL_SHA256" ]] || { echo "Whisper model SHA256 mismatch: $GOT" >&2; exit 6; }
  BYTES="$(wc -c < "$CACHE_MODEL" | tr -d ' ')"
  [[ "$BYTES" == "$WHISPER_MODEL_BYTES" ]] || { echo "Whisper model byte size mismatch: $BYTES" >&2; exit 6; }

  "$CACHE_BIN" --help >/dev/null 2>&1 || { echo "whisper-cli smoke help failed" >&2; exit 7; }
  python3 - "$CACHE_MANIFEST" "$WHISPER_TAG" "$WHISPER_COMMIT" "$WHISPER_MODEL_NAME" "$WHISPER_MODEL_SHA256" "$BYTES" "$ARCH" <<'PY'
import json,sys
path,tag,commit,model,sha,size,arch=sys.argv[1:]
with open(path,'w',encoding='utf-8') as f:
 json.dump({'engine':'whisper.cpp','whisper_tag':tag,'whisper_commit':commit,'model':model,'model_sha256':sha,'model_bytes':int(size),'architecture':arch},f,sort_keys=True,indent=2)
 f.write('\n')
PY
fi

case "$ARCH" in
  arm64) file "$CACHE_BIN" | grep -Eq 'arm64|Mach-O 64-bit executable arm64' ;;
  x86_64) file "$CACHE_BIN" | grep -Eq 'x86_64|Mach-O 64-bit executable x86_64' ;;
esac

LINKS="$(mktemp "${TMPDIR:-/tmp}/whisper-links.XXXXXX")"
otool -L "$CACHE_BIN" > "$LINKS"
tail -n +2 "$LINKS" | grep -E '/opt/homebrew|/usr/local/(Cellar|opt|lib)' && { echo "whisper-cli links against host package manager" >&2; cat "$LINKS" >&2; rm -f "$LINKS"; exit 8; } || true
rm -f "$LINKS"

rm -rf "$OUTPUT"
mkdir -p "$OUTPUT/bin" "$OUTPUT/models" "$OUTPUT/licenses"
cp "$CACHE_BIN" "$OUTPUT/bin/whisper-cli"
cp "$CACHE_MODEL" "$OUTPUT/models/$WHISPER_MODEL_NAME"
cp "$CACHE_MANIFEST" "$OUTPUT/RUNTIME.json"
if compgen -G "$CACHE/licenses/*" >/dev/null; then cp "$CACHE/licenses/"* "$OUTPUT/licenses/"; fi
cat > "$OUTPUT/MODEL_PROVENANCE.txt" <<EOF
Model: $WHISPER_MODEL_NAME
Source: $WHISPER_MODEL_URL
SHA-256: $WHISPER_MODEL_SHA256
Bytes: $WHISPER_MODEL_BYTES
Whisper.cpp tag: $WHISPER_TAG
Whisper.cpp commit: $WHISPER_COMMIT
EOF

echo "PASS: whisper.cpp $WHISPER_TAG ($WHISPER_COMMIT) + $WHISPER_MODEL_NAME -> $OUTPUT"
