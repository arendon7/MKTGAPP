#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m unittest tests.test_post_w99_canonical_change_evidence
python -m py_compile src/binario_marketing/service_post_w99_canonical_change_evidence_app.py
node --check web/canonical-change-evidence.js

grep -q 'service_post_w99_operator_session_progress_app' src/binario_marketing/service_post_w99_canonical_change_evidence_app.py
grep -q 'FIELDS_CHANGED' web/canonical-change-evidence.js
grep -q 'UNCHANGED' web/canonical-change-evidence.js
grep -q 'NO_LONGER_PRESENT' web/canonical-change-evidence.js
grep -q 'POST_W99_CANONICAL_CHANGE_EVIDENCE_FIELDS' web/canonical-change-evidence.js
grep -q 'main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53' docs/POST_W99_CANONICAL_CHANGE_EVIDENCE.md

if grep -Eq 'def do_(POST|PATCH|PUT|DELETE)' src/binario_marketing/service_post_w99_canonical_change_evidence_app.py; then
  echo 'Canonical Change Evidence service must remain GET/static-only' >&2
  exit 1
fi
if grep -Eq 'fetch\(|opsApi\(|XMLHttpRequest|sendBeacon|localStorage|setInterval|\.click\(\)|dispatchEvent\(|requestSubmit\(' web/canonical-change-evidence.js; then
  echo 'Canonical Change Evidence browser layer must remain zero-transport and non-executing' >&2
  exit 1
fi

echo 'Post-W99 Canonical Change Evidence audit PASS'
