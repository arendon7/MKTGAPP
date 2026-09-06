#!/bin/bash
set -euo pipefail

APP="${1:-}"
[[ -n "$APP" ]] || { echo 'POST-W99 DEV MAC AUDIT BLOCKED: app path required' >&2; exit 4; }
[[ -d "$APP" ]] || { echo 'POST-W99 DEV MAC AUDIT BLOCKED: app missing' >&2; exit 4; }

CONTENTS="$APP/Contents"
RESOURCES="$CONTENTS/Resources"
PLIST="$CONTENTS/Info.plist"
LAUNCH="$RESOURCES/launch.py"
PROVENANCE="$RESOURCES/POST_W99_DEV_BUILD.json"
PY="$RESOURCES/runtime/python/bin/python3"

[[ -x "$PY" ]] || { echo 'POST-W99 DEV MAC AUDIT BLOCKED: embedded Python missing' >&2; exit 4; }
[[ -f "$LAUNCH" && -f "$PROVENANCE" && -f "$PLIST" ]] || { echo 'POST-W99 DEV MAC AUDIT BLOCKED: dev metadata missing' >&2; exit 4; }

IDENTIFIER="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleIdentifier' "$PLIST")"
DISPLAY="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleDisplayName' "$PLIST")"
[[ "$IDENTIFIER" == 'com.sistemabinario.marketing.postw99dev' ]] || { echo "POST-W99 DEV MAC AUDIT BLOCKED: wrong bundle id $IDENTIFIER" >&2; exit 4; }
[[ "$DISPLAY" == 'Binario Marketing IA Post-W99 Dev' ]] || { echo "POST-W99 DEV MAC AUDIT BLOCKED: wrong display name $DISPLAY" >&2; exit 4; }

/usr/bin/grep -q 'from binario_marketing.service_post_w99_dev_app import serve' "$LAUNCH"
! /usr/bin/grep -q 'service_wave76_app' "$LAUNCH"
[[ -f "$RESOURCES/source/src/binario_marketing/social_process_lock.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/social_background.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_social_background_control_app.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_today_portfolio_app.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/cloud_social_bridge.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_cloud_social_bridge_app.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/inbox_attention.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_inbox_action_center_app.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_inbox_reply_reconciliation_app.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/inbox_crm_identity.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_inbox_crm_identity_app.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/results_freshness.py" ]]
[[ -f "$RESOURCES/source/src/binario_marketing/service_post_w99_results_freshness_guard_app.py" ]]
[[ -f "$RESOURCES/source/web/primary-navigation.js" ]]
[[ -f "$RESOURCES/source/web/social-background-control.js" ]]
[[ -f "$RESOURCES/source/web/today-portfolio.js" ]]
[[ -f "$RESOURCES/source/web/cloud-social-bridge.js" ]]
[[ -f "$RESOURCES/source/web/inbox-action-center.js" ]]
[[ -f "$RESOURCES/source/web/inbox-reply-reconciliation.js" ]]
[[ -f "$RESOURCES/source/web/inbox-crm-identity.js" ]]
/usr/bin/grep -q 'service_post_w99_results_freshness_guard_app' "$RESOURCES/source/src/binario_marketing/service_post_w99_dev_app.py"
/usr/bin/grep -q 'service_post_w99_inbox_crm_identity_app as base' "$RESOURCES/source/src/binario_marketing/service_post_w99_results_freshness_guard_app.py"
/usr/bin/grep -q 'ACTIVE_RESULTS_MAX_AGE_SECONDS = 24' "$RESOURCES/source/src/binario_marketing/results_freshness.py"
/usr/bin/grep -q 'CAPTURE_RESULTS' "$RESOURCES/source/src/binario_marketing/results_freshness.py"
/usr/bin/grep -q 'record_learning_decision' "$RESOURCES/source/src/binario_marketing/service_post_w99_results_freshness_guard_app.py"
/usr/bin/grep -q 'generate_ai_copilot' "$RESOURCES/source/src/binario_marketing/service_post_w99_results_freshness_guard_app.py"
! /usr/bin/grep -q 'MetaGraphClient' "$RESOURCES/source/src/binario_marketing/service_post_w99_results_freshness_guard_app.py"
/usr/bin/grep -q 'SocialProcessLock' "$RESOURCES/source/src/binario_marketing/cloud_social_bridge.py"
! /usr/bin/grep -q 'from gateway' "$RESOURCES/source/src/binario_marketing/cloud_social_bridge.py"
/usr/bin/grep -q '/api/portfolio-control-tower' "$RESOURCES/source/web/today-portfolio.js"
/usr/bin/grep -q 'Delegar a cloud' "$RESOURCES/source/web/cloud-social-bridge.js"
/usr/bin/grep -q 'window.confirm' "$RESOURCES/source/web/cloud-social-bridge.js"
! /usr/bin/grep -q 'setInterval' "$RESOURCES/source/web/cloud-social-bridge.js"
/usr/bin/grep -q 'refresh-attention' "$RESOURCES/source/web/inbox-action-center.js"
/usr/bin/grep -q "method:'POST'" "$RESOURCES/source/web/inbox-action-center.js"
! /usr/bin/grep -q 'setInterval' "$RESOURCES/source/web/inbox-action-center.js"
/usr/bin/grep -q 'reply-reconcile' "$RESOURCES/source/web/inbox-reply-reconciliation.js"
/usr/bin/grep -q 'provider_checked:true' "$RESOURCES/source/web/inbox-reply-reconciliation.js"
/usr/bin/grep -q 'window.confirm' "$RESOURCES/source/web/inbox-reply-reconciliation.js"
! /usr/bin/grep -q 'setInterval' "$RESOURCES/source/web/inbox-reply-reconciliation.js"
! /usr/bin/grep -q 'fetch.*meta' "$RESOURCES/source/web/inbox-reply-reconciliation.js"
/usr/bin/grep -q '/inbox-crm-identity.js' "$RESOURCES/source/src/binario_marketing/service_post_w99_inbox_crm_identity_app.py"
/usr/bin/grep -q 'crm-identity-link' "$RESOURCES/source/web/inbox-crm-identity.js"
/usr/bin/grep -q 'window.confirm' "$RESOURCES/source/web/inbox-crm-identity.js"
/usr/bin/grep -q 'provider_person_id' "$RESOURCES/source/web/inbox-crm-identity.js"
! /usr/bin/grep -q 'setInterval' "$RESOURCES/source/web/inbox-crm-identity.js"
! /usr/bin/grep -q 'setTimeout' "$RESOURCES/source/web/inbox-crm-identity.js"
! /usr/bin/grep -q 'MutationObserver' "$RESOURCES/source/web/inbox-crm-identity.js"
! /usr/bin/grep -q 'graph.facebook' "$RESOURCES/source/web/inbox-crm-identity.js"
/usr/bin/grep -q 'hmac.new' "$RESOURCES/source/src/binario_marketing/inbox_crm_identity.py"
/usr/bin/grep -q '0o600' "$RESOURCES/source/src/binario_marketing/inbox_crm_identity.py"
! /usr/bin/grep -q 'MetaGraph' "$RESOURCES/source/src/binario_marketing/service_post_w99_inbox_crm_identity_app.py"

"$PY" -I -B - "$PROVENANCE" <<'PY'
import json,sys
p=json.load(open(sys.argv[1], encoding='utf-8'))
assert p['schema']=='binario.marketing.post-w99-dev-build.v1', p
assert p['terminal']=='binario_marketing.service_post_w99_dev_app', p
assert p['canonical_w99_main']=='60ef38aa01c841c60f98b7dc79fcc9bb5d676e53', p
assert p['release_authority'] is False, p
assert p['physical_uat_authority'] is False, p
assert p['w100'] is False, p
print('POST-W99 DEV PROVENANCE PASS')
PY

/usr/bin/codesign --verify --deep --strict "$APP"
echo 'POST-W99 DEV MAC AUDIT PASS: current terminal includes cloud delegation + Inbox loop + CRM identity + results decision freshness guard'
