#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PIN_FILE="$ROOT/scripts/full_mac_python_runtime.env"
TARGET=""
REQUESTED_ARCH=""
ARCHIVE_OVERRIDE="${FULL_MAC_PYTHON_ARCHIVE:-}"

fail() { printf 'FULL MAC PYTHON BOOTSTRAP BLOCKED: %s\n' "$1" >&2; exit 3; }
pass() { printf 'PASS: %s\n' "$1"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) [[ $# -ge 2 ]] || fail "--target requires a directory"; TARGET="$2"; shift 2 ;;
    --arch) [[ $# -ge 2 ]] || fail "--arch requires arm64 or x86_64"; REQUESTED_ARCH="$2"; shift 2 ;;
    --archive) [[ $# -ge 2 ]] || fail "--archive requires a local tar.gz"; ARCHIVE_OVERRIDE="$2"; shift 2 ;;
    *) fail "unknown argument: $1" ;;
  esac
done

[[ "$(uname -s)" == "Darwin" ]] || fail "pinned FULL MAC runtime bootstrap must run on macOS"
[[ -f "$PIN_FILE" ]] || fail "runtime pin file missing: $PIN_FILE"
[[ -n "$TARGET" ]] || fail "--target is required"
# shellcheck disable=SC1090
source "$PIN_FILE"

normalize_arch() {
  case "$1" in
    arm64|aarch64) printf 'arm64\n' ;;
    x86_64|amd64) printf 'x86_64\n' ;;
    *) return 1 ;;
  esac
}

HOST_ARCH="$(normalize_arch "$(uname -m)")" || fail "unsupported Mac architecture: $(uname -m)"
if [[ -n "$REQUESTED_ARCH" ]]; then ARCH="$(normalize_arch "$REQUESTED_ARCH")" || fail "unsupported requested architecture: $REQUESTED_ARCH"; else ARCH="$HOST_ARCH"; fi
[[ "$ARCH" == "$HOST_ARCH" ]] || fail "cross-architecture runtime verification is forbidden; requested $ARCH on $HOST_ARCH"

case "$ARCH" in
  arm64) ASSET="$FULL_MAC_PYTHON_ARM64_ASSET"; EXPECTED_SHA256="$FULL_MAC_PYTHON_ARM64_SHA256"; URL="$FULL_MAC_PYTHON_ARM64_URL" ;;
  x86_64) ASSET="$FULL_MAC_PYTHON_X86_64_ASSET"; EXPECTED_SHA256="$FULL_MAC_PYTHON_X86_64_SHA256"; URL="$FULL_MAC_PYTHON_X86_64_URL" ;;
  *) fail "unsupported normalized architecture: $ARCH" ;;
esac

TMP="$(mktemp -d "${TMPDIR:-/tmp}/binario-full-mac-python.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT
ARCHIVE="$TMP/$ASSET"
EXTRACT="$TMP/extract"
mkdir -p "$EXTRACT"

if [[ -n "$ARCHIVE_OVERRIDE" ]]; then
  [[ -f "$ARCHIVE_OVERRIDE" ]] || fail "runtime archive override not found: $ARCHIVE_OVERRIDE"
  /bin/cp "$ARCHIVE_OVERRIDE" "$ARCHIVE"
else
  /usr/bin/curl --fail --location --retry 3 --silent --show-error --output "$ARCHIVE" "$URL"
fi
ACTUAL_SHA256="$(/usr/bin/shasum -a 256 "$ARCHIVE" | /usr/bin/awk '{print $1}')"
[[ "$ACTUAL_SHA256" == "$EXPECTED_SHA256" ]] || fail "runtime SHA256 mismatch for $ASSET"
pass "runtime archive SHA256 verified ($ARCH)"

/usr/bin/tar -xzf "$ARCHIVE" -C "$EXTRACT"
if [[ -x "$EXTRACT/python/bin/python3" ]]; then SOURCE_RUNTIME="$EXTRACT/python"; elif [[ -x "$EXTRACT/bin/python3" ]]; then SOURCE_RUNTIME="$EXTRACT"; else fail "verified runtime archive does not contain executable bin/python3"; fi
rm -rf "$TARGET"
mkdir -p "$(dirname "$TARGET")"
/usr/bin/ditto "$SOURCE_RUNTIME" "$TARGET"
[[ -x "$TARGET/bin/python3" ]] || fail "embedded runtime copy lost bin/python3"
/bin/ln -sf python3 "$TARGET/bin/python"

"$TARGET/bin/python3" -I -B - <<PY
import platform, sys
expected_version = tuple(map(int, "${FULL_MAC_PYTHON_VERSION}".split(".")))
assert sys.version_info[:3] == expected_version, (sys.version_info[:3], expected_version)
machine = platform.machine()
normalized = "arm64" if machine in {"arm64", "aarch64"} else "x86_64" if machine in {"x86_64", "amd64"} else machine
assert normalized == "${ARCH}", (normalized, "${ARCH}")
PY

cat > "$TARGET/FULL_MAC_PYTHON_RUNTIME.json" <<JSON
{
  "architecture": "$ARCH",
  "python_version": "$FULL_MAC_PYTHON_VERSION",
  "release": "$FULL_MAC_PYTHON_RELEASE",
  "schema": "binario.marketing.full-mac-python-runtime.v2",
  "source_asset": "$ASSET",
  "source_sha256": "$EXPECTED_SHA256",
  "upstream": "astral-sh/python-build-standalone"
}
JSON
pass "embedded CPython executes natively as $ARCH"
