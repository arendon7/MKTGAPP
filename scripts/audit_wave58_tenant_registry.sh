#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
SRC="$RES/source"
LAUNCH="$RES/launch.py"
SERVICE="$SRC/src/binario_marketing/service_wave58_app.py"
CLIENT="$SRC/src/binario_marketing/public_gateway_wave58.py"
UI="$SRC/web/public-gateway-wave58.js"
LOADER="$SRC/web/audiences-wave39-loader.js"
CORE="$SRC/gateway/versioned_service.py"
REGISTRY="$SRC/gateway/tenant_registry.py"
REMOTE="$SRC/gateway/supabase_tenant_registry.py"
ADMIN="$SRC/gateway/tenant_admin.py"
TENANT_API="$SRC/api/tenant.py"
SHARED="$SRC/api/_shared.py"
HEALTH="$SRC/api/health.py"
SQL="$SRC/gateway/supabase/002_tenant_credential_registry.sql"
for file in "$SERVICE" "$CLIENT" "$UI" "$LOADER" "$CORE" "$REGISTRY" "$REMOTE" "$ADMIN" "$TENANT_API" "$SHARED" "$HEALTH" "$SQL"; do
  [[ -f "$file" ]] || { echo "Wave 58 audit: missing $file" >&2; exit 3; }
done
W56_LINE="$(/usr/bin/grep -n 'service_wave56_app import serve' "$LAUNCH" | tail -1 | cut -d: -f1)"
W58_LINE="$(/usr/bin/grep -n 'service_wave58_app import serve' "$LAUNCH" | tail -1 | cut -d: -f1)"
[[ -n "$W56_LINE" && -n "$W58_LINE" && "$W58_LINE" -gt "$W56_LINE" ]] || { echo "Wave 58 audit: launcher must place Wave 58 after Wave 56" >&2; exit 3; }
/usr/bin/grep -q "tenant.src='/public-gateway-wave58.js'" "$LOADER" || { echo "Wave 58 audit: loader missing W58 tenant controls" >&2; exit 3; }
for text in 'Registro, rotación y revocación' 'Rotar secreto del sitio' 'Rotar pull del desktop' 'Revocar tenant' 'Reactivar + invalidar claves antiguas'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 58 audit: missing UI contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q 'X-Binario-Credential-Version' "$CLIENT" || { echo "Wave 58 audit: desktop credential-version header missing" >&2; exit 3; }
/usr/bin/grep -q 'X-Binario-Credential-Version' "$CORE" || { echo "Wave 58 audit: gateway credential-version header missing" >&2; exit 3; }
/usr/bin/grep -q 'number == 1' "$CORE" || { echo "Wave 58 audit: W56 version-1 compatibility gate missing" >&2; exit 3; }
/usr/bin/grep -q 'tenant is revoked' "$CORE" || { echo "Wave 58 audit: revocation authentication gate missing" >&2; exit 3; }
/usr/bin/grep -q 'credential version is stale' "$CORE" || { echo "Wave 58 audit: stale credential rejection missing" >&2; exit 3; }
/usr/bin/grep -q 'binario-gateway-v2:tenant-admin' "$REGISTRY" || { echo "Wave 58 audit: isolated admin derivation missing" >&2; exit 3; }
/usr/bin/grep -q 'master_secret_returned.*False' "$ADMIN" || { echo "Wave 58 audit: admin master-secret response boundary missing" >&2; exit 3; }
/usr/bin/grep -q 'secret_returned.*False' "$ADMIN" || { echo "Wave 58 audit: admin secret response boundary missing" >&2; exit 3; }
/usr/bin/grep -q 'SupabaseTenantCredentialRegistry' "$SHARED" || { echo "Wave 58 audit: deployed gateway does not use durable tenant registry" >&2; exit 3; }
/usr/bin/grep -q 'registry.healthcheck()' "$HEALTH" || { echo "Wave 58 audit: live health does not prove tenant registry readiness" >&2; exit 3; }
for marker in 'binario_gateway_tenants' 'binario_gateway_tenant_audit' 'security definer' 'set search_path = pg_catalog, public' 'binario_gateway_tenant_rotate' 'binario_gateway_tenant_revoke' 'binario_gateway_tenant_reactivate'; do
  /usr/bin/grep -qi "$marker" "$SQL" || { echo "Wave 58 audit: SQL contract missing: $marker" >&2; exit 3; }
done
[[ "$(/usr/bin/grep -ic 'enable row level security' "$SQL")" -ge 2 ]] || { echo "Wave 58 audit: both tenant tables must enable RLS" >&2; exit 3; }
[[ "$(/usr/bin/grep -ic 'revoke all on table.*anon, authenticated' "$SQL")" -ge 2 ]] || { echo "Wave 58 audit: public roles must be revoked from both tenant tables" >&2; exit 3; }
/usr/bin/grep -q 'grant execute on function public.binario_gateway_tenant_rotate(text, text) to service_role' "$SQL" || { echo "Wave 58 audit: service-role-only rotation RPC missing" >&2; exit 3; }
if /usr/bin/grep -Eq '^[[:space:]]*(secret|master_secret|ingress_secret|pull_secret|hmac_secret)[[:space:]]' "$SQL"; then echo "Wave 58 audit: tenant registry must not contain secret columns" >&2; exit 3; fi
/usr/bin/grep -q 'tenant_secret_persisted_in_registry.*False' "$SERVICE" || { echo "Wave 58 audit: desktop registry secret boundary missing" >&2; exit 3; }
/usr/bin/grep -q 'crm_mutations.*0' "$SERVICE" || { echo "Wave 58 audit: CRM zero-mutation contract missing" >&2; exit 3; }
/usr/bin/grep -q 'provider_mutations.*0' "$SERVICE" || { echo "Wave 58 audit: provider zero-mutation contract missing" >&2; exit 3; }
/usr/bin/grep -q 'background_polling.*False' "$SERVICE" || { echo "Wave 58 audit: explicit sync contract missing" >&2; exit 3; }
if /usr/bin/grep -q 'setInterval' "$UI"; then echo "Wave 58 audit: background polling is forbidden" >&2; exit 3; fi
if /usr/bin/grep -q "fetch('https://" "$UI"; then echo "Wave 58 audit: browser must not call public gateway directly" >&2; exit 3; fi
printf 'WAVE 58 TENANT CREDENTIAL REGISTRY AUDIT PASS\n'
