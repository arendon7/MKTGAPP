# Wave 57 · Gateway Deployment & Live Connectivity

Wave 57 operationalizes the Wave 56 public intake gateway without weakening the desktop boundary.

## Truth boundary

The macOS desktop remains loopback-only. Public traffic terminates at a separately deployed gateway. The gateway can only persist signed lead-intake envelopes in its remote queue; it cannot create CRM records, publish content, send messages, call Meta or activate Ads.

A source tree containing `api/`, `gateway/` and `vercel.json` is **deployable source**, not evidence that a public deployment exists. A live claim requires an explicit successful Wave 57 smoke against the deployed origin.

## Dedicated infrastructure

Use a dedicated Supabase project for the MERCADEO APP public intake queue. Do not reuse SANA, Greenatics Ops, Calcula tu Huella or other application databases.

Required Supabase migration:

`gateway/supabase/001_public_intake_queue.sql`

The migration must retain RLS, revoke direct `anon`/`authenticated` table access and preserve remote payload redaction after ACK or expiry.

Use a dedicated Vercel project for the public gateway source in this repository. Required server-side environment values are:

- `BINARIO_GATEWAY_MASTER_SECRET`
- `SUPABASE_URL`
- `SUPABASE_SECRET_KEY`

Never expose any of these values to browser JavaScript. The first-party website backend receives only the tenant-derived ingress secret produced by the desktop for that company.

## Deployment gates

Before claiming the gateway live:

1. Dedicated Supabase project is ACTIVE_HEALTHY.
2. Queue migration is applied exactly once and advisors are reviewed after DDL.
3. Dedicated Vercel project is deployed from the certified source tree.
4. Vercel server environment contains the three required values.
5. `/api/health` returns `binario.marketing.public-gateway-health.v1` with `status=ok`.
6. Run `scripts/wave57_gateway_live_smoke.py` with a synthetic, non-customer event.
7. Smoke must prove signed ingress, authenticated pull, envelope signature/hash verification and ACK.
8. ACK must remove/redact the synthetic payload remotely.
9. No real customer PII is required by the smoke.
10. Only after those gates may the deployment URL be configured in the desktop and an explicit empty/synthetic sync be performed.

## Canonical live smoke

The smoke reads configuration from arguments or environment:

```text
BINARIO_GATEWAY_URL=https://<dedicated-project>.vercel.app
BINARIO_GATEWAY_TENANT_ID=tenant_<24hex>
BINARIO_GATEWAY_MASTER_SECRET=<same installation master secret configured in gateway>
PYTHONPATH=src python scripts/wave57_gateway_live_smoke.py
```

The script creates one synthetic event named `Binario Wave 57 Deployment Smoke`, verifies it through the signed pull channel and ACKs it by default. It never invokes the local CRM or any marketing provider. It prints only secret-free JSON evidence.

Use `--no-ack` only for debugging; a certification run should ACK its synthetic event.

## Required evidence

Record at minimum:

- certified source tree SHA;
- Git commit deployed;
- Supabase project ref and region;
- Vercel project/deployment id and immutable deployment URL;
- migration applied result;
- security/performance advisor result;
- `/api/health` result;
- Wave 57 smoke output;
- final desktop explicit sync result;
- confirmation that production release gates remain unchanged.

## Release status

Wave 57 does not change the product release boundary. The desktop remains `0.9.0.dev1`, development channel, ad-hoc signed, not notarized, without stable release tag and without production/v1.0 claim.
