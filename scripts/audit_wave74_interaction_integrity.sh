#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave74_interaction_integrity.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$SRC/src/binario_marketing/service_wave74_app.py" ]]
[[ -f "$SRC/web/interaction-probe.js" ]]
[[ -f "$SRC/web/interaction-audit.js" ]]
[[ -f "$LAUNCH" && -x "$PYTHON" ]]
/usr/bin/grep -q 'service_wave74_app import serve' "$LAUNCH"
/usr/bin/grep -q 'binario.marketing.interaction-integrity.v1' "$SRC/src/binario_marketing/service_wave74_app.py"
/usr/bin/grep -q 'EventTarget.prototype.addEventListener' "$SRC/web/interaction-probe.js"
/usr/bin/grep -q 'Auditar controles' "$SRC/web/interaction-audit.js"
/usr/bin/grep -q 'wave74RunInteractionAudit' "$SRC/web/interaction-audit.js"
! /usr/bin/grep -q 'setInterval' "$SRC/web/interaction-audit.js"
! /usr/bin/grep -q 'RELEASE_READY = True' "$SRC/src/binario_marketing/service_wave74_app.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$PYTHON" -I -B - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]);data=Path(sys.argv[2])/'data'
sys.path.insert(0,str(source/'src'))
from binario_marketing.service_wave74_app import AppRuntime, INTERACTION_ASSETS
runtime=AppRuntime.create(source,data)
try:
    first=runtime.interaction_integrity()
    assert first['ready'], first['missing']
    assert len(first['assets']) == len(INTERACTION_ASSETS) == 2
    company=runtime.create_company({'name':'Wave 74 Audit'})
    report=runtime.interaction_integrity(company['id'])
    assert report['ready'], report['missing']
    assert report['company']['id'] == company['id']
    assert len(report['browser_contract']['views']) == 12
    assert report['browser_contract']['programmatic_clicks'] is False
    assert report['browser_contract']['form_submission'] is False
finally:
    if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
    runtime.proxies.shutdown();runtime.transcriptions.shutdown();runtime.renders.shutdown()
PY
echo 'WAVE 74 INTERACTION INTEGRITY AUDIT PASS'
