#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
UI="$SRC/web/results-intelligence.js"
SERVICE="$SRC/src/binario_marketing/service_wave65_app.py"
for file in "$UI" "$SERVICE"; do
  [[ -f "$file" ]] || { echo "Wave 65 audit: missing $file" >&2; exit 3; }
done
/usr/bin/grep -q 'service_wave65_app import serve' "$RES/launch.py" || { echo "Wave 65 audit: Mac launch is not using Wave 65" >&2; exit 3; }
/usr/bin/grep -q "intelligence.src='/results-intelligence.js'" "$SERVICE" || { echo "Wave 65 audit: runtime bootstrap missing results bundle" >&2; exit 3; }
/usr/bin/grep -q 'data-results-intelligence-wave65' "$SERVICE" || { echo "Wave 65 audit: idempotent bootstrap marker missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave64_app as base' "$SERVICE" || { echo "Wave 65 audit: Wave 64 compatibility base missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.results-intelligence.v1' "$SERVICE" || { echo "Wave 65 audit: schema missing" >&2; exit 3; }
for text in 'Resultados & IA' 'Evidencia determinística primero' 'LAST_CAPTURED_TOUCH' 'Solo requieren atención' 'Analizar con IA' 'La IA no publicará, activará pauta ni ejecutará decisiones'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 65 audit: missing UX contract: $text" >&2; exit 3; }
done
for text in '"provider_read_performed": False' '"provider_mutation_performed": False' '"ai_generation_performed": False' '"decision_execution_performed": False' '"automatic_recommendation_execution": False' '"background_polling": False' '"cloud_required": False'; do
  /usr/bin/grep -q "$text" "$SERVICE" || { echo "Wave 65 audit: missing safety contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q '127.0.0.1' "$SERVICE" || { echo "Wave 65 audit: loopback default missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI" "$SERVICE"; then echo "Wave 65 audit: polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 65 audit: UI must not call external endpoints directly" >&2; exit 3; fi
if /usr/bin/grep -q 'sendBeacon' "$UI"; then echo "Wave 65 audit: beaconing is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q 'def do_POST' "$SERVICE" || /usr/bin/grep -q 'def do_PATCH' "$SERVICE" || /usr/bin/grep -q 'def do_DELETE' "$SERVICE"; then echo "Wave 65 audit: service must not introduce mutation routes" >&2; exit 3; fi
if /usr/bin/grep -Eq "method:[[:space:]]*['\"](PATCH|PUT|DELETE)['\"]" "$UI"; then echo "Wave 65 audit: results UI must not mutate marketing state directly" >&2; exit 3; fi
POST_COUNT="$(/usr/bin/grep -o "method:'POST'" "$UI" | /usr/bin/wc -l | tr -d ' ')"
[[ "$POST_COUNT" == "1" ]] || { echo "Wave 65 audit: exactly one explicit POST is allowed" >&2; exit 3; }
/usr/bin/grep -q '/ai/generate' "$UI" || { echo "Wave 65 audit: explicit POST must reuse certified AI generation" >&2; exit 3; }
if /usr/bin/grep -q '/learning/refresh' "$UI"; then echo "Wave 65 audit: provider metric refresh belongs to canonical Results surface" >&2; exit 3; fi
if /usr/bin/grep -Eiq 'SUPABASE_[A-Z_]+|VERCEL_[A-Z_]+' "$UI" "$SERVICE"; then echo "Wave 65 audit: results intelligence must not require cloud credentials" >&2; exit 3; fi
printf 'WAVE 65 RESULTS INTELLIGENCE AUDIT PASS\n'
