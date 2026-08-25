#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)";cd "$ROOT";export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v tests.test_post_w99_pipeline_priority tests.test_post_w99_navigator tests.test_post_w99_dev_entrypoint
python3 -m py_compile src/binario_marketing/cli.py src/binario_marketing/service_post_w99_action_center_app.py src/binario_marketing/service_post_w99_pipeline_priority_app.py src/binario_marketing/service_post_w99_navigator_app.py
node --check web/action-center.js
node --check web/navigator.js
python3 - <<'PY'
from pathlib import Path
cli=Path('src/binario_marketing/cli.py').read_text();doc=Path('docs/POST_W99_DEV_ENTRYPOINT.md').read_text()
assert 'from .service import serve' in cli
assert 'from .service_post_w99_navigator_app import serve' in cli
assert 'serve-dev' in cli
assert 'No debe interpretarse como W100' in doc
print('POST-W99 DEV RUNTIME AUDIT PASS')
PY
