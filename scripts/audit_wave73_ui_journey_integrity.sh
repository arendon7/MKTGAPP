#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave73_ui_journey_integrity.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$SRC/src/binario_marketing/service_wave73_app.py" ]]
[[ -f "$SRC/web/product-bootstrap.js" ]]
[[ -f "$SRC/web/product-entry-wave73.js" ]]
[[ -f "$SRC/web/product-journey.js" ]]
[[ -f "$LAUNCH" && -x "$PYTHON" ]]
/usr/bin/grep -q 'service_wave73_app import serve' "$LAUNCH"
/usr/bin/grep -q 'binario.marketing.ui-integrity.v1' "$SRC/src/binario_marketing/service_wave73_app.py"
/usr/bin/grep -q 'wave73BootstrapPromise' "$SRC/web/product-bootstrap.js"
/usr/bin/grep -q 'Verificar interfaz' "$SRC/web/product-journey.js"
/usr/bin/grep -q 'wave73RunJourneyCheck' "$SRC/web/product-journey.js"
! /usr/bin/grep -q 'setInterval' "$SRC/web/product-bootstrap.js"
! /usr/bin/grep -q 'setInterval' "$SRC/web/product-journey.js"
! /usr/bin/grep -q 'RELEASE_READY = True' "$SRC/src/binario_marketing/service_wave73_app.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$PYTHON" -I -B - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]);data=Path(sys.argv[2]) / "data"
sys.path.insert(0,str(source / "src"))
from binario_marketing.service_wave73_app import AppRuntime, UI_ASSETS, UI_VIEWS
runtime=AppRuntime.create(source,data)
try:
    report=runtime.ui_integrity()
    assert report["ready"], report["missing"]
    assert report["deterministic_bootstrap"] is True
    assert report["inventory"]["present_ui_assets"] == len(UI_ASSETS)
    assert report["inventory"]["declared_views"] == len(UI_VIEWS) == 12
    company=runtime.create_company({"name":"Wave 73 Audit"})
    report=runtime.ui_integrity(company["id"])
    assert report["ready"], report["missing"]
    assert report["company"]["id"] == company["id"]
    assert report["safety"]["browser_check_executes_external_actions"] is False
finally:
    if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
    runtime.proxies.shutdown();runtime.transcriptions.shutdown();runtime.renders.shutdown()
PY

echo 'WAVE 73 UI JOURNEY INTEGRITY AUDIT PASS'
