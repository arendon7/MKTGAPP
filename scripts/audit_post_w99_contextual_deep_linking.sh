#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SERVICE="src/binario_marketing/service_post_w99_contextual_deep_linking_app.py"
UI="web/contextual-deep-linking.js"
DOC="docs/POST_W99_CONTEXTUAL_DEEP_LINKING.md"
DEV="src/binario_marketing/service_post_w99_dev_app.py"

for path in "$SERVICE" "$UI" "$DOC" "$DEV"; do
  test -f "$path" || { echo "FAIL missing $path" >&2; exit 1; }
done

grep -q 'service_post_w99_execution_return_app as base' "$SERVICE"
grep -q 'contextual-deep-linking.js' "$SERVICE"
grep -q 'service_post_w99_contextual_deep_linking_app' "$DEV"
grep -q "target_kind='ACTIVITY'" "$UI"
grep -q "target_kind='PUBLICATION'" "$UI"
grep -q "target_kind='CAMPAIGN_EXECUTION'" "$UI"
grep -q 'TARGET_NOT_FOUND' "$UI"
grep -q 'OWNER_ONLY' "$UI"
grep -q 'Action Center priority' "$DOC"
grep -q '60ef38aa01c841c60f98b7dc79fcc9bb5d676e53' "$DOC"

if grep -Eq "method:'(POST|PATCH|PUT|DELETE)'|fetch\(|opsApi\(|setInterval|sendBeacon|\.click\(|dispatchEvent\(" "$UI"; then
  echo 'FAIL contextual layer gained transport, polling, or synthetic execution' >&2
  exit 1
fi
if grep -Eq '^\s*def do_(POST|PATCH|PUT|DELETE)' "$SERVICE"; then
  echo 'FAIL contextual service gained a mutation handler' >&2
  exit 1
fi

node --check "$UI"
PYTHONPATH=src python -m unittest tests.test_post_w99_contextual_deep_linking -v

echo 'POST-W99 CONTEXTUAL DEEP LINKING AUDIT PASS'
