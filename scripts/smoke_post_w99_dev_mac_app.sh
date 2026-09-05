#!/bin/bash
set -euo pipefail

APP="${1:-}"
PORT="${BINARIO_POST_W99_SMOKE_PORT:-18766}"
[[ -n "$APP" ]] || { echo 'POST-W99 DEV MAC SMOKE BLOCKED: app path required' >&2; exit 4; }
[[ "$(uname -s)" == "Darwin" ]] || { echo 'POST-W99 DEV MAC SMOKE BLOCKED: macOS required' >&2; exit 4; }
[[ -d "$APP" ]] || { echo 'POST-W99 DEV MAC SMOKE BLOCKED: app missing' >&2; exit 4; }

EXEC="$APP/Contents/MacOS/Binario Marketing IA"
PLIST="$APP/Contents/Info.plist"
[[ -x "$EXEC" && -f "$PLIST" ]] || { echo 'POST-W99 DEV MAC SMOKE BLOCKED: bundle is incomplete' >&2; exit 4; }
IDENTIFIER="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$PLIST")"
[[ "$IDENTIFIER" == 'com.sistemabinario.marketing.postw99dev' ]] || { echo 'POST-W99 DEV MAC SMOKE BLOCKED: not the isolated post-W99 development app' >&2; exit 4; }

TMP="$(/usr/bin/mktemp -d "${TMPDIR:-/tmp}/binario-post-w99-smoke.XXXXXX")"
DATA="$TMP/data"
FAKE_HOME="$TMP/home"
LOG="$TMP/app.log"
mkdir -p "$DATA" "$FAKE_HOME"
AGENT="$FAKE_HOME/Library/LaunchAgents/com.sistemabinario.marketing.social-scheduler.plist"
BASE="http://127.0.0.1:$PORT"
PID=""
cleanup(){
  if [[ -n "$PID" ]]; then
    /bin/kill "$PID" 2>/dev/null || true
    wait "$PID" 2>/dev/null || true
  fi
  /bin/rm -rf "$TMP"
}
trap cleanup EXIT

test ! -e "$AGENT"
HOME="$FAKE_HOME" BINARIO_IA_HOME="$DATA" BINARIO_NO_BROWSER=1 BINARIO_PORT="$PORT" \
  "$EXEC" >"$LOG" 2>&1 &
PID=$!

READY=0
for _ in $(seq 1 100); do
  if /usr/bin/curl --fail --silent "$BASE/api/health" > "$TMP/health.json"; then
    READY=1
    break
  fi
  if ! /bin/kill -0 "$PID" 2>/dev/null; then
    cat "$LOG" >&2
    echo 'POST-W99 DEV MAC SMOKE BLOCKED: app exited before health became ready' >&2
    exit 4
  fi
  sleep 0.2
done
[[ "$READY" == "1" ]] || { cat "$LOG" >&2; echo 'POST-W99 DEV MAC SMOKE BLOCKED: health timeout' >&2; exit 4; }

/usr/bin/curl --fail --silent "$BASE/api/social/background" > "$TMP/background.json"
/usr/bin/curl --fail --silent "$BASE/api/portfolio-control-tower" > "$TMP/portfolio.json"
/usr/bin/curl --fail --silent "$BASE/primary-navigation.js" > "$TMP/primary-navigation.js"
/usr/bin/curl --fail --silent "$BASE/social-background-control.js" > "$TMP/social-background-control.js"
/usr/bin/curl --fail --silent "$BASE/today-portfolio.js" > "$TMP/today-portfolio.js"

/usr/bin/grep -q 'status' "$TMP/health.json"
/usr/bin/grep -q 'platform_supported' "$TMP/background.json"
/usr/bin/grep -q 'binario.marketing.portfolio-control-tower.v1' "$TMP/portfolio.json"
/usr/bin/grep -q 'POST_W99_PRIMARY_NAVIGATION' "$TMP/primary-navigation.js"
/usr/bin/grep -q 'Hoy' "$TMP/primary-navigation.js"
/usr/bin/grep -q 'Resultados' "$TMP/primary-navigation.js"
/usr/bin/grep -q 'Astra / IA' "$TMP/primary-navigation.js"
/usr/bin/grep -q 'Activar en este Mac' "$TMP/social-background-control.js"
/usr/bin/grep -q 'window.confirm' "$TMP/social-background-control.js"
/usr/bin/grep -q '/today-portfolio.js' "$TMP/social-background-control.js"
/usr/bin/grep -q '/api/portfolio-control-tower' "$TMP/today-portfolio.js"
/usr/bin/grep -q 'slice(0,5)' "$TMP/today-portfolio.js"
/usr/bin/grep -q 'Volver a todas las empresas' "$TMP/today-portfolio.js"

# Smoke is read-only with respect to launchd integration: no install/remove endpoint is invoked.
test ! -e "$AGENT"
[[ -z "$(find "$FAKE_HOME/Library/LaunchAgents" -type f 2>/dev/null || true)" ]]

/bin/kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
PID=""

echo 'POST-W99 DEV MAC SMOKE PASS: packaged terminal + Today portfolio + background status; no automatic LaunchAgent install'
