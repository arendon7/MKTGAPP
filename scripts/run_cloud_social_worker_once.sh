#!/bin/sh
set -eu

fail() {
  printf '%s\n' "CLOUD SOCIAL WORKER DEPLOY BLOCKED: $1" >&2
  exit 64
}

case "${BINARIO_SOCIAL_WORKER_ENABLED:-}" in
  0|1) ;;
  *) fail "BINARIO_SOCIAL_WORKER_ENABLED must equal 0 or 1" ;;
esac
[ -n "${BINARIO_SOCIAL_WORKER_TENANTS:-}" ] || fail "BINARIO_SOCIAL_WORKER_TENANTS is required"
[ -n "${SUPABASE_URL:-}" ] || fail "SUPABASE_URL is required"
case "$SUPABASE_URL" in
  https://*) ;;
  *) fail "SUPABASE_URL must use HTTPS" ;;
esac
if [ -z "${SUPABASE_SECRET_KEY:-}" ] && [ -z "${SUPABASE_SERVICE_ROLE_KEY:-}" ]; then
  fail "SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY is required"
fi
[ -n "${META_ACCESS_TOKEN:-}" ] || fail "META_ACCESS_TOKEN is required for a headless cloud worker"

# ENABLED=0 is an intentional configuration smoke: CloudSocialWorker.run_once()
# returns DISABLED before resolving Meta or claiming database work. ENABLED=1 is
# the only execution mode with publication authority. No secret value is printed.
exec python -m binario_marketing.cloud_social_worker
