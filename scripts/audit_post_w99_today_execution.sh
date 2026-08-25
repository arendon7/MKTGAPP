#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v tests.test_post_w99_today_execution tests.test_post_w99_dev_entrypoint
python3 -m py_compile src/binario_marketing/service_post_w99_today_execution_app.py src/binario_marketing/service_post_w99_dev_app.py
if command -v node >/dev/null 2>&1; then node --check web/today-execution.js; fi
python3 - <<'PY'
from pathlib import Path
service=Path('src/binario_marketing/service_post_w99_today_execution_app.py').read_text()
ui=Path('web/today-execution.js').read_text()
doc=Path('docs/POST_W99_TODAY_EXECUTION.md').read_text()
assert 'service_post_w99_integrated_cockpit_app as base' in service
assert 'FIRST_N_CANONICAL_ACTION_CENTER_ITEMS' in service
assert 'canonical_order_preserved' in service
assert 'completion_occurs_in_owner_module' in service
assert 'main' in doc and 'W100' in doc
assert 'def do_POST' not in service and 'def do_PATCH' not in service and 'def do_DELETE' not in service
for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", 'setInterval', 'sendBeacon'):
    assert forbidden not in ui, forbidden
print('POST-W99 TODAY EXECUTION AUDIT PASS')
PY
