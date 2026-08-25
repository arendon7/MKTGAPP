#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v tests.test_post_w99_execution_return tests.test_post_w99_today_execution tests.test_post_w99_dev_entrypoint
python3 -m py_compile src/binario_marketing/service_post_w99_execution_return_app.py src/binario_marketing/service_post_w99_today_execution_app.py src/binario_marketing/service_post_w99_dev_app.py
if command -v node >/dev/null 2>&1; then node --check web/execution-return.js; node --check web/today-execution.js; fi
python3 - <<'PY'
from pathlib import Path
service=Path('src/binario_marketing/service_post_w99_execution_return_app.py').read_text()
ui=Path('web/execution-return.js').read_text()
doc=Path('docs/POST_W99_EXECUTION_RETURN.md').read_text()
assert 'service_post_w99_today_execution_app as base' in service
assert 'execution-return.js' in service
assert 'sessionStorage' in ui and 'localStorage.setItem' not in ui
assert 'STILL_IN_TODAY' in ui and 'STILL_PENDING' in ui and 'NO_LONGER_PENDING' in ui
assert 'actionCenterLoad(true)' in ui and 'todayLoad(true)' in ui
assert 'owner module remains completion authority' in doc
assert 'main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53' in doc
assert 'def do_POST' not in service and 'def do_PATCH' not in service and 'def do_DELETE' not in service and 'def do_PUT' not in service
for forbidden in ("method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'", 'setInterval', 'sendBeacon', 'fetch('):
    assert forbidden not in ui, forbidden
print('POST-W99 EXECUTION RETURN AUDIT PASS')
PY
