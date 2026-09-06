# Post-W99 Desktop → Cloud Social Bridge

This increment connects the existing local publication queue to the remote social queue without allowing the local scheduler and the cloud worker to own the same publication at the same time.

## Authority handoff

The critical ordering is:

1. validate the local publication and cloud-compatible payload;
2. persist a secret-free `PREPARED` delegation sidecar;
3. acquire the same OS process lock used by local social publishing;
4. transition the canonical local publication from `QUEUED` to `DELEGATED`;
5. release the local process lock;
6. only then call `POST /api/social_enqueue`.

`SocialStore.due()` accepts only `QUEUED`, so a `DELEGATED` publication is invisible to the desktop scheduler and LaunchAgent. `start_publish()` also cannot transition from `DELEGATED`.

If the process/network fails after step 4 but before remote confirmation, the row remains `DELEGATED` and the sidecar remains `PREPARED`. This deliberately prefers a stopped publication over a possible duplicate. The operator can explicitly retry the idempotent enqueue later.

## Process race protection

The bridge uses `SocialProcessLock`, the same kernel-backed lock used by the local publisher. If another local process owns the publication queue, delegation fails before creating a sidecar or changing `QUEUED`.

Once `DELEGATED` is durable, the lock can be released before network IO because the local publisher no longer considers the row eligible.

## Existing gateway credentials are reused

No second desktop credential system is introduced.

Per-company routing continues to use the existing `PublicGatewayConfigStore` (`gateway_url + tenant_id`) and the existing installation-level `GatewayCredentialStore` master secret in environment/Keychain. The bridge derives a purpose-separated HMAC secret using:

`binario-gateway-v1:social:<tenant_id>`

Only that derived secret signs `/api/social_enqueue` and `/api/social_status`. Neither the master secret nor the derived secret is written to the delegation sidecar or returned to browser code.

The desktop implementation intentionally does not import the server `gateway.*` package. This keeps the packaged macOS runtime valid with its existing `source/src` Python path. Contract tests compare desktop and server derivation to prevent protocol drift.

## Delegation sidecar

`State/cloud-social-delegations/<publication_id>.json` contains only:

- company/publication identity;
- canonical gateway origin and tenant;
- canonical remote-job SHA-256;
- delegation/remote status;
- remote provider object ID after confirmed success;
- the boolean `provider_outcome_ambiguous`;
- timestamps and sanitized transport exception type.

It never stores publication message, media/link URLs, gateway credentials, Meta credentials, authorization headers or provider error bodies.

## Remote reconciliation

The signed cloud status API now exposes `provider_outcome_ambiguous` as a boolean while continuing to hide provider error text and lease details.

- `PENDING` / `LEASED`: local remains `DELEGATED`.
- `PUBLISHED` with remote ID: local becomes `PUBLISHED`.
- `FAILED`, ambiguity false: local becomes `FAILED`; any new queue attempt is a later explicit human action.
- `FAILED`, ambiguity true: local remains `DELEGATED` and sidecar becomes `AMBIGUOUS`; automatic/local retry remains impossible until manual reconciliation.
- remote 404 while never confirmed: remains `PREPARED`, eligible only for explicit idempotent retry.
- remote 404 after prior confirmation: becomes `AMBIGUOUS`.

There is no automatic status polling in this increment.

## Operator controls

The existing editorial calendar receives an additive control layer:

- `QUEUED`: **Delegar a cloud**, with explicit confirmation explaining that local authority is withdrawn first;
- `DELEGATED`: **Estado cloud**; if enqueue is still `PREPARED`, a second explicit action becomes **Reintentar cloud**.

No control auto-clicks, polls, schedules or invokes provider operations directly from the browser.

## Post-W99 macOS bundle

The development builder/audit/smoke now require:

- `cloud_social_bridge.py`;
- `service_post_w99_cloud_social_bridge_app.py`;
- `cloud-social-bridge.js`;
- the current `service_post_w99_dev_app` terminal.

The smoke test only fetches the browser asset; it does not delegate, retry or refresh a publication and does not alter LaunchAgent state.

## Deployment boundary

This bridge makes the desktop capable of handing approved work to a remote queue. It does not create a Vercel project, deploy Supabase migrations, provision server secrets, configure a scheduler or enable the cloud worker in production.

The connected Vercel account is currently Hobby and has no project, so no frequent Vercel Cron is assumed or embedded in this source increment.

## Release boundary

This is post-W99 development only. Canonical `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, v0.9.0, Physical UAT evidence and release authority remain unchanged. This is not W100.
