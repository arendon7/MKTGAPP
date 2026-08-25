#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JS="$ROOT/web/contextual-action-handoff.js"
SERVICE="$ROOT/src/binario_marketing/service_post_w99_contextual_action_handoff_app.py"
DOC="$ROOT/docs/POST_W99_CONTEXTUAL_ACTION_HANDOFF.md"
DEV="$ROOT/src/binario_marketing/service_post_w99_dev_app.py"

for path in "$JS" "$SERVICE" "$DOC" "$DEV"; do
  test -f "$path" || { echo "missing: $path" >&2; exit 1; }
done

grep -q "service_post_w99_portfolio_cadence_app as base" "$SERVICE"
grep -q "/portfolio-cadence.js" "$SERVICE"
grep -q "/contextual-action-handoff.js" "$SERVICE"
grep -q "service_post_w99_contextual_action_handoff_app" "$DEV"
grep -q "ACTION_READY" "$JS"
grep -q "CONTROL_NOT_FOUND" "$JS"
grep -q "NO_ACTION_MAPPING" "$JS"
grep -q "portfolio_cadence_never_reprioritizes" "$DOC"
grep -q "control_absence_is_not_completion" "$DOC"
grep -q "main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53" "$DOC"

if grep -Eq 'opsApi\(|fetch\(|\.click\(' "$JS"; then
  echo "FAIL: handoff browser layer owns transport or synthetic execution" >&2
  exit 1
fi
if grep -Eq 'do_POST|do_PATCH|do_PUT|do_DELETE' "$SERVICE"; then
  echo "FAIL: terminal service adds mutation handler" >&2
  exit 1
fi

echo "POST-W99 CONTEXTUAL ACTION HANDOFF AUDIT PASS"
