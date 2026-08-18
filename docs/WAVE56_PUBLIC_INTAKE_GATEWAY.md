# Wave 56 · Public Intake Gateway

Wave 56 closes the network boundary between Internet-facing lead forms and the local BINARIO Marketing IA desktop application without pretending that localhost is publicly reachable.

## Truth boundary

The desktop application continues to bind to loopback only. Wave 56 does **not** expose the Mac as a public webhook, does not open a tunnel, and does not run provider polling in the background.

The public gateway is a separately deployable, stateless HTTP layer backed by a durable queue. Its authority is intentionally narrow:

1. accept a signed lead event;
2. persist it in the remote intake queue;
3. return pending signed envelopes to an authenticated desktop pull;
4. acknowledge imported events and redact their remote payload.

It cannot create CRM contacts or opportunities, publish content, send messages, activate Ads, or call marketing providers.

## Flow

```text
Landing page / form
  └─ W54 captures utm_* + bm_tid in first-party fields
      └─ site's trusted backend
          └─ POST /api/intake (signed)
              └─ remote durable queue
                  └─ explicit desktop “Sincronizar ahora”
                      ├─ POST /api/pull (signed)
                      ├─ verify envelope signature + SHA-256
                      ├─ validate bm_tid / UTM against W53 canonical tracking link
                      ├─ write W55 Lead Intake locally
                      └─ POST /api/ack only for successfully stored events
```

Receiving a remote event is still **not** CRM conversion. W55 remains the explicit conversion gate.

## Credentials and tenant separation

There is one installation-level master secret. It is supplied to the gateway as server environment variable:

```text
BINARIO_GATEWAY_MASTER_SECRET
```

On macOS the same master secret is read from the `gateway` Keychain namespace, unless the same environment variable is supplied. The master secret is never written to company/application JSON.

Wave 56 deterministically derives two different per-tenant HMAC keys:

```text
ingress_secret = HMAC-SHA256(master, "binario-gateway-v1:ingress:<tenant_id>")
pull_secret    = HMAC-SHA256(master, "binario-gateway-v1:pull:<tenant_id>")
```

The external site's trusted backend may receive only the **ingress secret** for its tenant. It never receives the master secret or pull secret. No secret belongs in browser JavaScript, HTML, a query string, analytics metadata, or `bm_tid`.

## Tenant and event identifiers

```text
tenant_<24 lowercase hex>
evt_<32 lowercase hex>
```

An external backend must generate a new cryptographically random `event_id` for each logical submission and reuse that same ID only when retrying the same event.

## Signed request contract

All authenticated requests use HMAC-SHA256 v1. The request signing input is UTF-8:

```text
v1\n
<unix_timestamp_seconds>\n
<nonce_or_event_id>\n
<UPPERCASE_METHOD>\n
<canonical_path>\n
<sha256(raw_request_body)>
```

The HMAC key is the derived tenant secret. The signature header is:

```text
X-Binario-Signature: v1=<lowercase hex HMAC>
```

Every authenticated request also includes:

```text
X-Binario-Tenant: tenant_<24hex>
X-Binario-Timestamp: <Unix seconds>
```

For public intake, the event itself is the replay/idempotency nonce:

```text
X-Binario-Event: evt_<32hex>
```

For desktop pull/ack, use a random 16-byte nonce encoded as 32 lowercase hex:

```text
X-Binario-Nonce: <32hex>
```

The accepted clock skew is at most 300 seconds. The server rejects stale/future requests outside that window. `(tenant_id, event_id)` is the durable idempotency key. Replaying the exact same event with the exact same canonical payload returns an idempotent success; reusing the event id with a different payload fails closed.

## Public intake payload

`POST /api/intake`

Maximum body: 64 KiB.

```json
{
  "schema": "binario.marketing.public-lead.v1",
  "external_ref": "optional-site-submission-id",
  "lead": {
    "name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "+57 300 000 0000",
    "source": "website",
    "attribution_capture": {
      "bm_tid": "bm_...",
      "utm_source": "instagram",
      "utm_medium": "paid_social",
      "utm_campaign": "...",
      "utm_id": "...",
      "utm_content": "...",
      "utm_term": "...",
      "utm_source_platform": "..."
    }
  }
}
```

Allowed lead fields are deliberately bounded: name, organization, role, email, phone, WhatsApp, Instagram, source, tags, notes, and attribution capture. Credential-like fields are rejected recursively.

The gateway does **not** decide campaign attribution. The desktop later validates `bm_tid` and supplied UTM values against the immutable W53 TrackingLink before accepting the lead.

## Pull envelope

`POST /api/pull`

The desktop uses the derived pull secret. Each returned event has schema:

```text
binario.marketing.public-intake-envelope.v1
```

and contains:

- tenant id;
- event id;
- gateway receive time;
- original public-lead payload;
- canonical payload SHA-256;
- an envelope signature created with the pull secret.

The desktop re-hashes and re-verifies every envelope before local intake.

## ACK semantics

`POST /api/ack` is sent only for events that passed all local verification and were durably written to W55 Lead Intake.

If local validation or persistence fails, the event is **not acknowledged** and remains available for a later explicit retry.

If local intake succeeds but ACK transport fails, the next pull is safe: the deterministic local `source_ref` is:

```text
public_gateway:<tenant_id>:<event_id>
```

so the repeated local intake is idempotent and the ACK can be retried without creating a second lead.

A successful ACK sets the remote event to `ACKED` and redacts `body_json` to `NULL`. Hash, event id, tenant id and timing metadata remain for auditability.

## Retention

Pending PII is retained for at most 30 days by the application contract. Pull performs opportunistic expiry: expired pending rows become `EXPIRED` and their `body_json` is redacted. A later infrastructure wave may add a scheduled database cleanup job, but Wave 56 does not claim background cleanup or polling.

## Supabase queue

Apply:

```text
gateway/supabase/001_public_intake_queue.sql
```

The migration creates `public.binario_public_intake_queue`, enables RLS, revokes table access from `anon` and `authenticated`, and grants the backend role only the operations the gateway requires.

Gateway server environment:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=<server-only secret key>
BINARIO_GATEWAY_MASTER_SECRET=<same master secret as the Mac installation>
```

`SUPABASE_SERVICE_ROLE_KEY` is accepted only as a legacy backend fallback. Neither Supabase backend credential is exposed to browser code or persisted in the desktop product state.

A dedicated Supabase project is recommended for this gateway. Wave 56 source does not silently reuse unrelated existing projects.

## Vercel deployment

The deployable serverless entrypoints are:

```text
api/intake.py
api/pull.py
api/ack.py
api/health.py
```

`vercel.json` keeps the serverless gateway bundle separate from the large desktop application surfaces. Configure the three server environment variables above in the Vercel project before using a real deployment.

The health endpoint is public and secret-free. Intake/pull/ack remain authenticated.

## Desktop configuration

The W56 workspace **Gateway público** supports:

1. configure an HTTPS gateway origin and company tenant id;
2. create or store the master secret in macOS Keychain;
3. explicitly reveal the tenant ingress secret when provisioning a trusted site backend;
4. manually run `Sincronizar ahora`;
5. inspect imported/failing counts without exposing secrets.

The ingress secret is displayed only after an explicit local action. It is labeled server-to-server and unsafe for browser embedding.

## Safety invariants

- desktop remains loopback-local;
- no public desktop webhook;
- no browser-held gateway secret;
- no Supabase server secret in browser source;
- HMAC-authenticated ingress/pull/ack;
- timestamp replay window;
- event-level idempotency;
- tenant-scoped derived secrets;
- remote lead PII redacted after ACK/expiry;
- gateway cannot mutate CRM;
- gateway cannot call marketing providers;
- remote intake does not imply campaign attribution;
- desktop validates attribution canonically before ACK;
- no automatic CRM conversion;
- no automatic message, publication, or Ads action;
- no background polling;
- only explicit desktop sync mutates local Lead Intake.

## Deployment status

Wave 56 makes the gateway **deployable and testable**, but source certification alone does not mean a public endpoint has been provisioned. A dedicated Supabase/Vercel deployment must be configured, migration-applied, smoke-tested and then bound to a company before it can truthfully be called live.

The desktop build remains `0.9.0.dev1`, development channel, arm64 iteration, ad-hoc signed and not notarized. Wave 56 is not a v1.0/production release.
