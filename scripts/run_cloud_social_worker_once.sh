#!/bin/sh
set -eu

fail() {
  printf '%s\n' "CLOUD SOCIAL WORKER DEPLOY BLOCKED: $1" >&2
  exit 64
}

[ "${BINARIO_SOCIAL_WORKER_ENABLED:-}" = "1" ] || fail "BINARIO_SOCIAL_WORKER_ENABLED must equal 1"
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

# The worker itself validates tenant syntax, numeric bounds and provider configuration.
# No secret value is ever printed by this wrapper.
exec python -m binario_marketing.cloud_social_worker
