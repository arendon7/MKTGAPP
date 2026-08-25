#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)";cd "$ROOT";export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -m unittest -v tests.test_post_w99_pipeline_priority tests.test_post_w99_navigator
python3 -m py_compile src/binario_marketing/service_post_w99_pipeline_priority_app.py src/binario_marketing/service_post_w99_navigator_app.py
node --check web/action-center.js
node --check web/navigator.js
python3 - <<'PY'
from pathlib import Path
s=Path('src/binario_marketing/service_post_w99_navigator_app.py').read_text();u=Path('web/navigator.js').read_text();d=Path('docs/POST_W99_NAVIGATOR.md').read_text()
assert 'service_post_w99_pipeline_priority_app as base' in s
assert 'semantic_embeddings": False' in s and 'ai_ranking": False' in s
for value in ("method:'POST'","method:'PATCH'","method:'PUT'","method:'DELETE'",'setInterval','sendBeacon'):assert value not in u
assert 'No modifica `main`' in d
print('POST-W99 NAVIGATOR AUDIT PASS')
PY
