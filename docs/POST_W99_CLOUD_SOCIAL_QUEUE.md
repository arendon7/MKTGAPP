# Post-W99 Cloud Social Queue

This increment establishes the durable remote scheduling contract required to publish while the desktop computer is offline. It deliberately does **not** execute Meta requests yet.

## Boundary

The remote queue is separate from `binario_public_intake_queue`. Inbound leads and outbound social execution never share a table, state machine or payload schema.

A cloud job is accepted only when its signed caller later proves the tenant identity and the payload declares the canonical local source state as `QUEUED` with explicit operator approval. This increment implements the queue/state contract; HTTP/HMAC ingress and provider execution remain later increments.

## Cloud-eligible publication v1

Only provider-ready, secret-free shapes are eligible:

- Facebook Page: text, link, public HTTPS image.
- Instagram: public HTTPS image or Reel.
- Local filesystem paths are forbidden.
- Facebook local Reel is intentionally excluded until media staging exists in cloud storage.
- Provider credentials, API keys, cookies, bearer tokens and service-role values are forbidden recursively.

The original 32-hex publication ID is the idempotency key inside a tenant. The canonical payload SHA-256 must match on reuse; changing the payload under the same publication ID fails with conflict.

## Worker leasing

`PENDING → LEASED → PUBLISHED` is the success path. A retryable failure returns to `PENDING` with exponential backoff. Non-retryable errors and the fifth failed attempt end at `FAILED`.

A worker lease contains a one-time random token. Only its SHA-256 is durable. Supabase claiming is atomic through `binario_claim_social_publish_jobs(...)`, using `FOR UPDATE SKIP LOCKED`, so concurrent workers cannot legitimately claim the same row.

Expired leases are recovered. After the attempt cap they fail closed instead of looping forever.

## Supabase security

`binario_social_publish_queue` has RLS enabled and grants no table access to `anon` or `authenticated`. The atomic claim RPC revokes execution from `PUBLIC`, `anon` and `authenticated`; only `service_role` may execute it.

The future runtime adapter must continue using server-side Supabase credentials only. The browser and durable publication payload must never receive the service-role key or Meta credentials.

## Validation base

Final PR validation is intentionally triggered after the isolated post-W99 macOS bundle landed in `dev/post-w99-action-center@f86a2a9fcb3ca04c808a32af2740d6f4daa88ed6`. This queue remains independent of that bundle but is certified against the same current development line.

## Next increment

The next safe step is a Supabase storage adapter + signed server-only enqueue/status API. Only after that contract is proven should a worker be allowed to resolve Meta credentials and invoke `MetaSocialPublisher`-equivalent provider operations.

## Release boundary

This is post-W99 development only. It does not modify canonical `main`, W99, v0.9.0, Physical UAT evidence, release authority or the three canonical GitHub workflows. It is not W100.
