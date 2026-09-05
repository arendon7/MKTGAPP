# Post-W99 Cloud Social API

This increment connects the certified remote social queue contract to server-only Supabase persistence and two signed Vercel endpoints. It still performs **zero Meta requests**.

## Endpoints

- `POST /api/social_enqueue`
  - maximum 64 KiB
  - accepts only `binario.marketing.remote-social-job.v1`
  - requires the queue contract's explicit `QUEUED` + operator-approved state
  - returns the queue receipt; exact replays remain publication-ID idempotent
- `POST /api/social_status`
  - maximum 4 KiB
  - body is exactly `{ "publication_id": "<32 hex>" }`
  - returns only sanitized execution state
  - never returns publication body, lease token/hash or provider error text

GET/PATCH/DELETE are not execution surfaces.

## Authentication

Both calls use the existing Binario HMAC request format:

- `X-Binario-Tenant`
- `X-Binario-Timestamp`
- `X-Binario-Nonce`
- `X-Binario-Signature`

The secret is tenant-specific and purpose-separated:

`HMAC-SHA256(BINARIO_GATEWAY_MASTER_SECRET, "binario-gateway-v1:social:<tenant_id>")`

The master secret remains server-side. A future desktop provisioning increment may place only the derived social tenant secret in Keychain. It must never copy the gateway master secret, Supabase service-role key or Meta credential to durable publication state.

Timestamp skew remains bounded to the existing five-minute gateway window. A verbatim enqueue replay inside that window is safe because the canonical publication ID + payload digest contract is idempotent. Status is read-only.

## Supabase adapter

`SupabaseSocialQueueStorage` uses only the isolated `binario_social_publish_queue` table. It refuses non-atomic distributed list/replace methods. Future workers must claim through `binario_claim_social_publish_jobs(...)`.

`SUPABASE_URL` must be a credential-free HTTPS origin. `SUPABASE_SECRET_KEY` / service-role credentials are used only in server request headers and are never placed in a query string, response payload or queue body.

## Authority boundary

This increment can enqueue and observe approved remote jobs. It cannot:

- resolve Meta credentials;
- call Graph API;
- claim a publication as a worker through public HTTP;
- mark a job published/failed through public HTTP;
- upload media;
- reply to comments/messages;
- activate ads.

Provider execution remains a later server-worker increment after lease-bound completion RPCs and credential isolation are proven.

## Release boundary

Post-W99 development only. Canonical W99 `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, v0.9.0 Physical UAT and the three canonical GitHub workflows remain untouched. This is not W100.
