#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m unittest tests.test_post_w99_campaign_execution_owner_drift_guard
python -m py_compile src/binario_marketing/service_post_w99_campaign_execution_owner_drift_guard_app.py
node --check web/campaign-execution-owner-drift-guard.js

grep -q 'service_post_w99_campaign_media_candidate_selection_handoff_app' src/binario_marketing/service_post_w99_campaign_execution_owner_drift_guard_app.py
grep -q 'CANONICAL_TARGET_NOT_PRESENT' src/binario_marketing/service_post_w99_campaign_execution_owner_drift_guard_app.py
grep -q 'no_target_does_not_select_replacement' src/binario_marketing/service_post_w99_campaign_execution_owner_drift_guard_app.py
grep -q 'OWNER_STATE_DRIFT' web/campaign-execution-owner-drift-guard.js
grep -q 'TARGET_NOT_EXACT' web/campaign-execution-owner-drift-guard.js
grep -q 'main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53' docs/POST_W99_CAMPAIGN_EXECUTION_OWNER_DRIFT_GUARD.md

if grep -Eq 'def do_(POST|PATCH|PUT|DELETE)' src/binario_marketing/service_post_w99_campaign_execution_owner_drift_guard_app.py; then
  echo 'Owner Drift Guard must remain GET/read-only' >&2
  exit 1
fi
if grep -Eq 'fetch\(|XMLHttpRequest|sendBeacon|localStorage|sessionStorage|setInterval|\.click\(\)|dispatchEvent\(' web/campaign-execution-owner-drift-guard.js; then
  echo 'Owner Drift Guard browser layer must remain zero-transport and non-persistent' >&2
  exit 1
fi

echo 'Post-W99 Campaign Execution Owner Drift Guard audit PASS'
