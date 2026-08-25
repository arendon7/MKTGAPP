#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v tests.test_post_w99_action_center tests.test_post_w99_pipeline_priority
python3 -m py_compile src/binario_marketing/service_post_w99_action_center_app.py src/binario_marketing/service_post_w99_pipeline_priority_app.py
if command -v node >/dev/null 2>&1; then node --check web/action-center.js; fi
python3 - <<'PY'
from pathlib import Path
source=Path('src/binario_marketing/service_post_w99_pipeline_priority_app.py').read_text()
doc=Path('docs/POST_W99_PIPELINE_PRIORITY.md').read_text()
assert 'service_post_w99_action_center_app as base' in source
assert 'def do_POST' not in source and 'def do_PATCH' not in source and 'def do_DELETE' not in source
assert 'NO se calcula probabilidad de cierre' in doc
assert 'opportunity_value_not_used_as_priority_score' in source
print('POST-W99 PIPELINE PRIORITY AUDIT PASS')
PY
