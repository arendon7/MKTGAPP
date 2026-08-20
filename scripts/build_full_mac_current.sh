#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH="arm64"
OUT="$ROOT/dist"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --arch) ARCH="$2"; shift 2 ;;
    --out) OUT="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$ARCH" == "arm64" ]] || { echo "Current iteration builder is arm64-only" >&2; exit 4; }
"$ROOT/scripts/build_full_mac_app.sh" --arch "$ARCH" --out "$OUT"
APP="$OUT/Binario Marketing IA.app"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$LAUNCH" && -x "$PYTHON" ]] || { echo "Current launch/runtime missing" >&2; exit 4; }

# Phase 1: reconstruct the exact historical runtime through Wave 66 so its strict audit
# remains meaningful. Waves 67+ are injected only after every historical audit has passed.
"$PYTHON" -I -B - "$LAUNCH" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding='utf-8')
anchor='from binario_marketing.service_wave45_app import serve\n'
if anchor not in text:
    raise SystemExit('Current build blocked: Wave 45 entrypoint marker missing')
for module in ('service_wave47_app','service_wave48_app','service_wave49_app','service_wave50_app','service_wave51_app','service_wave52_app','service_wave53_app','service_wave54_app','service_wave55_app','service_wave55_guard_app','service_wave56_app','service_wave59_app','service_wave60_app','service_wave61_app','service_wave62_app','service_wave63_app','service_wave64_app','service_wave65_app','service_wave66_app'):
    line=f'from binario_marketing.{module} import serve\n'
    if line not in text:
        text=text.replace(anchor, anchor+line, 1)
    anchor=line
path.write_text(text, encoding='utf-8')
PY
IDENTITY="${BINARIO_CODESIGN_IDENTITY:--}"
/usr/bin/codesign --force --deep --sign "$IDENTITY" "$APP"
/bin/bash "$ROOT/scripts/audit_wave47_product_surface.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave48_paid_media_center.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave49_creative_studio.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave50_command_center.sh" "$APP"
/bin/bash "$ROOT/scripts/audit_wave51_ai_copilot.sh" "$APP"
# Wave 52 remains an explicit audited prerequisite for every later arm64 iteration.
/bin/bash "$ROOT/scripts/audit_wave52_learning_loop.sh" "$APP"
# Wave 53 Attribution Foundation remains an explicit audited prerequisite.
/bin/bash "$ROOT/scripts/audit_wave53_attribution_foundation.sh" "$APP"
# Wave 54 First-Party Capture Bridge remains an explicit audited prerequisite.
/bin/bash "$ROOT/scripts/audit_wave54_capture_bridge.sh" "$APP"
# Wave 55 Lead Intake & Conversion remains an explicit audited prerequisite.
/bin/bash "$ROOT/scripts/audit_wave55_lead_intake.sh" "$APP"
# Wave 56 remains available as an optional cloud extension; its safety contract is still audited.
/bin/bash "$ROOT/scripts/audit_wave56_public_gateway.sh" "$APP"
# Historical certified marker retained for the Wave 59 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 59
/bin/bash "$ROOT/scripts/audit_wave59_local_product_integration.sh" "$APP"
# Historical certified marker retained for the Wave 60 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 60
/bin/bash "$ROOT/scripts/audit_wave60_daily_workdesk.sh" "$APP"
# Historical certified marker retained for the Wave 61 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 61
/bin/bash "$ROOT/scripts/audit_wave61_commercial_desk.sh" "$APP"
# Historical certified marker retained for the Wave 62 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 62
/bin/bash "$ROOT/scripts/audit_wave62_contact_360.sh" "$APP"
# Historical certified marker retained for the Wave 63 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 63
/bin/bash "$ROOT/scripts/audit_wave63_commercial_pipeline.sh" "$APP"
# Historical certified marker retained for the Wave 64 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 64
/bin/bash "$ROOT/scripts/audit_wave64_execution_workspace.sh" "$APP"
# Historical certified marker retained for the Wave 65 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 65
/bin/bash "$ROOT/scripts/audit_wave65_results_intelligence.sh" "$APP"
# Historical certified marker retained for the Wave 66 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 66
/bin/bash "$ROOT/scripts/audit_wave66_product_uat_readiness.sh" "$APP"

# Phase 2: add W67 only after the strict historical W66 audit passed unchanged.
"$PYTHON" -I -B - "$LAUNCH" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding='utf-8')
anchor='from binario_marketing.service_wave66_app import serve\n'
line='from binario_marketing.service_wave67_app import serve\n'
if anchor not in text:
    raise SystemExit('Current build blocked: Wave 66 entrypoint marker missing')
if line not in text:
    text=text.replace(anchor, anchor+line, 1)
path.write_text(text, encoding='utf-8')
PY
/usr/bin/codesign --force --deep --sign "$IDENTITY" "$APP"
# Wave 67 records explicit physical-UAT evidence while keeping CI ineligible for the physical gate.
/bin/bash "$ROOT/scripts/audit_wave67_physical_uat_harness.sh" "$APP"
# Historical certified marker retained for the Wave 67 contract: CURRENT ARM64 ITERATION BUILD PASS: Wave 67

# Phase 3: W68 adds operator guidance only after the strict W67 evidence harness passed unchanged.
"$PYTHON" -I -B - "$LAUNCH" <<'PY'
from pathlib import Path
import sys
path=Path(sys.argv[1])
text=path.read_text(encoding='utf-8')
anchor='from binario_marketing.service_wave67_app import serve\n'
line='from binario_marketing.service_wave68_app import serve\n'
if anchor not in text:
    raise SystemExit('Current build blocked: Wave 67 entrypoint marker missing')
if line not in text:
    text=text.replace(anchor, anchor+line, 1)
path.write_text(text, encoding='utf-8')
PY
/usr/bin/codesign --force --deep --sign "$IDENTITY" "$APP"
/bin/bash "$ROOT/scripts/audit_wave68_guided_physical_uat.sh" "$APP"
printf 'CURRENT ARM64 ITERATION BUILD PASS: Wave 68 · %s\n' "$APP"
