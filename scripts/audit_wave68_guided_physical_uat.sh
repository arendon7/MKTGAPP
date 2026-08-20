#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave68_guided_physical_uat.sh <app>}"
RES="$APP/Contents/Resources"
SRC="$RES/source"
LAUNCH="$RES/launch.py"
SERVICE="$SRC/src/binario_marketing/service_wave68_app.py"
UI="$SRC/web/guided-physical-uat.js"
[[ -f "$SERVICE" && -f "$UI" && -f "$LAUNCH" ]] || { echo 'Wave 68 bundle files missing' >&2; exit 1; }
/usr/bin/grep -q 'service_wave68_app import serve' "$LAUNCH"
/usr/bin/grep -q 'service_wave67_app as base' "$SERVICE"
/usr/bin/grep -q 'guided-physical-uat.js' "$SERVICE"
/usr/bin/grep -q 'data-guided-physical-uat-wave68' "$SERVICE"
/usr/bin/grep -q 'PRECONDICIÓN' "$UI"
/usr/bin/grep -q 'RESULTADO ESPERADO' "$UI"
/usr/bin/grep -q 'Abrir módulo' "$UI"
/usr/bin/grep -q 'ESCENARIO' "$UI"
! /usr/bin/grep -q "method:'POST'" "$UI"
! /usr/bin/grep -q "method:'PATCH'" "$UI"
! /usr/bin/grep -q 'setInterval' "$UI"
! /usr/bin/grep -q 'sendBeacon' "$UI"
! /usr/bin/grep -qi 'supabase\|vercel' "$UI"
printf 'WAVE 68 GUIDED PHYSICAL UAT AUDIT PASS\n'
