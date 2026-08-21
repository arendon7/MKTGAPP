#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave76_sandbox_functional_journey.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$SRC/src/binario_marketing/service_wave76_app.py" ]]
[[ -f "$SRC/web/uat-functional-journey.js" ]]
[[ -f "$LAUNCH" && -x "$PYTHON" ]]
/usr/bin/grep -q 'service_wave76_app import serve' "$LAUNCH"
/usr/bin/grep -q 'binario.marketing.uat-sandbox-journey.v1' "$SRC/src/binario_marketing/service_wave76_app.py"
/usr/bin/grep -q 'state_observation_only' "$SRC/src/binario_marketing/service_wave76_app.py"
/usr/bin/grep -q 'FUNCTIONAL JOURNEY VALIDATOR · W76' "$SRC/web/uat-functional-journey.js"
/usr/bin/grep -q 'Verificar cambios' "$SRC/web/uat-functional-journey.js"
! /usr/bin/grep -q 'setInterval' "$SRC/web/uat-functional-journey.js"
! /usr/bin/grep -q '/api/meta/' "$SRC/web/uat-functional-journey.js"
! /usr/bin/grep -q '/ai/generate' "$SRC/web/uat-functional-journey.js"
! /usr/bin/grep -Eq "method:[[:space:]]*['\"](POST|PATCH|DELETE)['\"]" "$SRC/web/uat-functional-journey.js"
! /usr/bin/grep -q 'RELEASE_READY = True' "$SRC/src/binario_marketing/service_wave76_app.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$PYTHON" -I -B - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]);data=Path(sys.argv[2])/'data'
sys.path.insert(0,str(source/'src'))
from binario_marketing.service_wave76_app import AppRuntime
runtime=AppRuntime.create(source,data)
try:
    empty=runtime.uat_sandbox_journey()
    assert empty['summary']['core_required'] == 0, empty
    sandbox=runtime.create_uat_sandbox({})
    cid=sandbox['company']['id']; entities=sandbox['entities']
    initial=runtime.uat_sandbox_journey()
    assert initial['schema'] == 'binario.marketing.uat-sandbox-journey.v1'
    assert initial['summary']['core_required'] == 6, initial
    assert initial['summary']['core_verified'] == 2, initial
    assert initial['summary']['core_complete'] is False
    by_code={row['code']:row for row in initial['checkpoints']}
    assert by_code['EXACT_MATCH_HANDOFF']['status'] == 'READY_TO_TEST'
    assert by_code['NEW_LEAD_HANDOFF']['status'] == 'READY_TO_TEST'
    assert by_code['PIPELINE_STAGE_SAVE']['status'] == 'READY_TO_TEST'
    assert by_code['FOLLOWUP_INTERACTION']['status'] == 'READY_TO_TEST'
    assert by_code['RESULTS_EVIDENCE']['status'] == 'EXTERNAL_OPTIONAL'
    contact_id=entities['contact_id']
    runtime.convert_lead(cid, entities['matched_lead_id'], {'action':'LINK_CONTACT','contact_id':contact_id})
    runtime.convert_lead(cid, entities['new_lead_id'], {'action':'CREATE_CONTACT'})
    runtime.crm.update_opportunity(cid, entities['opportunity_id'], {'stage':'INTERESTED'})
    runtime.crm.complete_activity(cid, entities['activity_id'])
    final=runtime.uat_sandbox_journey()
    assert final['summary']['core_complete'] is True, final
    assert final['summary']['core_verified'] == 6, final
    by_code={row['code']:row for row in final['checkpoints']}
    for code in ('FIXTURE_INTEGRITY','EXACT_MATCH_HANDOFF','NEW_LEAD_HANDOFF','PIPELINE_STAGE_SAVE','FOLLOWUP_INTERACTION','CAMPAIGN_CONTEXT'):
        assert by_code[code]['status'] == 'VERIFIED', (code,by_code[code])
    assert final['safety']['read_only_projection'] is True
    assert final['safety']['provider_read_performed'] is False
    assert runtime.physical_uat.list(cid) == []
finally:
    if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
    runtime.proxies.shutdown();runtime.transcriptions.shutdown();runtime.renders.shutdown()
PY
echo 'WAVE 76 SANDBOX FUNCTIONAL JOURNEY AUDIT PASS'
