#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave72_product_entry_integrity.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$SRC/src/binario_marketing/service_wave72_app.py" ]]
[[ -f "$SRC/web/product-entry.js" ]]
[[ -f "$SRC/web/index.html" ]]
[[ -f "$LAUNCH" && -x "$PYTHON" ]]
/usr/bin/grep -q 'service_wave72_app import serve' "$LAUNCH"
/usr/bin/grep -q 'binario.marketing.product-integrity.v1' "$SRC/src/binario_marketing/service_wave72_app.py"
/usr/bin/grep -q 'data-product-entry-wave72' "$SRC/src/binario_marketing/service_wave72_app.py"
/usr/bin/grep -q '+ Empresa' "$SRC/web/product-entry.js"
/usr/bin/grep -q 'marketing-company-change' "$SRC/web/product-entry.js"
/usr/bin/grep -q 'marketing-ops-refreshed' "$SRC/web/product-entry.js"
/usr/bin/grep -q 'wave72BroadcastContext' "$SRC/web/product-entry.js"
! /usr/bin/grep -q 'setInterval' "$SRC/web/product-entry.js"
! /usr/bin/grep -q 'RELEASE_READY = True' "$SRC/src/binario_marketing/service_wave72_app.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$PYTHON" -I -B - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]);data=Path(sys.argv[2]) / "data"
sys.path.insert(0,str(source / "src"))
from binario_marketing.service_wave72_app import AppRuntime
runtime=AppRuntime.create(source,data)
try:
    initial=runtime.product_integrity()
    assert initial["ready"], initial["missing"]
    assert initial["inventory"]["required_web_assets"] == 46
    assert initial["inventory"]["present_web_assets"] == 46
    assert initial["inventory"]["required_runtime_methods"] == 33
    assert initial["inventory"]["implemented_runtime_methods"] == 33
    assert initial["inventory"]["registered_apps"] >= 12
    company=runtime.create_company({"name":"Wave 72 Audit"})
    report=runtime.product_integrity(company["id"])
    assert report["ready"], report["missing"]
    assert report["inventory"]["company_projection_checks"] == 27
    assert report["inventory"]["company_projection_pass"] == 27
    assert report["missing"] == {"web_assets":[],"runtime_methods":[],"failed_company_projections":[]}
finally:
    if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
    runtime.proxies.shutdown();runtime.transcriptions.shutdown();runtime.renders.shutdown()
PY

echo 'WAVE 72 PRODUCT ENTRY & JOURNEY INTEGRITY AUDIT PASS'
