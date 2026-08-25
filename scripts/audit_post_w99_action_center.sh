#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v tests.test_post_w99_action_center
python3 -m py_compile src/binario_marketing/service_post_w99_action_center_app.py
if command -v node >/dev/null 2>&1; then node --check web/action-center.js; fi
python3 - <<'PY'
from pathlib import Path
service=Path('src/binario_marketing/service_post_w99_action_center_app.py').read_text()
ui=Path('web/action-center.js').read_text()
assert 'service_wave76_app as base' in service
assert 'def do_POST' not in service and 'def do_PATCH' not in service and 'def do_DELETE' not in service
for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", 'setInterval', 'sendBeacon'):
    assert forbidden not in ui, forbidden
print('POST-W99 ACTION CENTER AUDIT PASS')
PY
