#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave75_controlled_uat_sandbox.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
PYTHON="$APP/Contents/Resources/runtime/python/bin/python3"
[[ -f "$SRC/src/binario_marketing/service_wave75_app.py" ]]
[[ -f "$SRC/src/binario_marketing/uat_sandbox_store.py" ]]
[[ -f "$SRC/web/uat-sandbox.js" ]]
[[ -f "$LAUNCH" && -x "$PYTHON" ]]
/usr/bin/grep -q 'service_wave75_app import serve' "$LAUNCH"
/usr/bin/grep -q 'binario.marketing.uat-sandbox-status.v1' "$SRC/src/binario_marketing/service_wave75_app.py"
/usr/bin/grep -q 'physical_release_evidence_allowed": False' "$SRC/src/binario_marketing/uat_sandbox_store.py"
/usr/bin/grep -q 'synthetic UAT sandbox is functional-only' "$SRC/src/binario_marketing/service_wave75_app.py"
/usr/bin/grep -q 'SINTÉTICO · NO RELEASE' "$SRC/web/uat-sandbox.js"
/usr/bin/grep -q 'window.confirm' "$SRC/web/uat-sandbox.js"
! /usr/bin/grep -q 'setInterval' "$SRC/web/uat-sandbox.js"
! /usr/bin/grep -q '/api/meta/' "$SRC/web/uat-sandbox.js"
! /usr/bin/grep -q '/ai/generate' "$SRC/web/uat-sandbox.js"
! /usr/bin/grep -q 'RELEASE_READY = True' "$SRC/src/binario_marketing/service_wave75_app.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
"$PYTHON" -I -B - "$SRC" "$TMP" <<'PY'
from pathlib import Path
import sys
source=Path(sys.argv[1]);data=Path(sys.argv[2])/'data'
sys.path.insert(0,str(source/'src'))
from binario_marketing.service_wave75_app import AppRuntime
runtime=AppRuntime.create(source,data)
try:
    real=runtime.create_company({'name':'Wave 75 Real Audit'})
    first=runtime.create_uat_sandbox({})
    assert first['functional_ready'], first
    assert first['contract']['synthetic_data'] is True
    assert first['contract']['physical_release_evidence_allowed'] is False
    cid=first['company']['id']
    company=runtime.companies.get(cid)
    assert company.facebook_page_id is None and company.instagram_id is None and company.ad_account_id is None
    leads=runtime.lead_intake_payload(cid)['leads']
    states={row['id']:row['status'] for row in leads}
    assert states[first['entities']['matched_lead_id']] == 'MATCHED', states
    assert states[first['entities']['new_lead_id']] == 'NEW', states
    assert len(runtime.crm.list_opportunities(cid)) == 1
    assert len(runtime.crm.list_activities(cid)) == 1
    campaigns=runtime.campaigns.list(cid)
    assert len(campaigns) == 1 and campaigns[0].status == 'IN_PROGRESS'
    try:
        runtime.start_physical_uat(cid, {'operator':'audit'})
    except ValueError as exc:
        assert 'functional-only' in str(exc)
    else:
        raise AssertionError('sandbox unexpectedly accepted physical UAT evidence')
    second=runtime.reset_uat_sandbox({'confirm':True})
    assert second['generation'] == first['generation'] + 1
    assert runtime.companies.get(cid).active is False
    assert runtime.companies.get(real['id']).active is True
finally:
    if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
    runtime.proxies.shutdown();runtime.transcriptions.shutdown();runtime.renders.shutdown()
PY
echo 'WAVE 75 CONTROLLED UAT SANDBOX AUDIT PASS'
