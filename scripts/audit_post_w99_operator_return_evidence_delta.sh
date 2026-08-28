#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m unittest tests.test_post_w99_operator_return_evidence_delta
python -m py_compile src/binario_marketing/service_post_w99_operator_return_evidence_delta_app.py
node --check web/operator-return-evidence-delta.js

grep -q 'service_post_w99_operator_current_priority_continuity_app' src/binario_marketing/service_post_w99_operator_return_evidence_delta_app.py
grep -q "script.src='/operator-return-evidence-delta.js'" src/binario_marketing/service_post_w99_operator_return_evidence_delta_app.py
grep -q 'FIELDS_CHANGED' web/operator-return-evidence-delta.js
grep -q 'ACTION_NOT_PRESENT_AFTER_REREAD' web/operator-return-evidence-delta.js
grep -q 'completion_claimed:false' web/operator-return-evidence-delta.js
grep -q 'causal_change_claimed:false' web/operator-return-evidence-delta.js
grep -q 'provider_freshness_claimed:false' web/operator-return-evidence-delta.js
grep -q 'main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53' docs/POST_W99_OPERATOR_RETURN_EVIDENCE_DELTA.md

if grep -Eq 'def do_(POST|PATCH|PUT|DELETE)' src/binario_marketing/service_post_w99_operator_return_evidence_delta_app.py; then
  echo 'Return Evidence Delta service must remain GET-only' >&2
  exit 1
fi
if grep -Eq 'fetch\(|opsApi\(|XMLHttpRequest|sendBeacon|localStorage|setInterval|\.click\(|dispatchEvent\(|requestSubmit\(' web/operator-return-evidence-delta.js; then
  echo 'Return Evidence Delta must remain zero-transport and non-executing' >&2
  exit 1
fi
if grep -Eq 'row\.title|row\.detail|reason\?\.explanation' web/operator-return-evidence-delta.js; then
  echo 'Return Evidence Delta snapshot must remain whitelist-only' >&2
  exit 1
fi

echo 'Post-W99 Operator Return Evidence Delta audit PASS'
