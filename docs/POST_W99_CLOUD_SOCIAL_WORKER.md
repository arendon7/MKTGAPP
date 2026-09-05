# Post-W99 Cloud Social Worker Core

This increment adds the first server-side execution authority for the remote social queue. The authority is deliberately narrow: a one-shot worker may publish only jobs that already passed the secret-free `binario.marketing.remote-social-job.v1` contract, are due, belong to an explicit tenant allowlist, and were atomically leased by Supabase.

## Safety boundary

The worker is disabled unless `BINARIO_SOCIAL_WORKER_ENABLED=1` and `BINARIO_SOCIAL_WORKER_TENANTS` contains one or more canonical tenant IDs. Meta credentials are resolved before any queue claim. Missing provider configuration therefore consumes no attempt and no lease.

The worker never receives the gateway master secret, browser credentials or a generic database update surface. Supabase service-role credentials remain inside the server-side storage adapter. Meta credentials are resolved by the existing `MetaGraphClient.from_env()` path; the worker does not implement or persist a second Meta credential system.

## Distributed execution protocol

1. `binario_claim_social_publish_jobs(...)` atomically claims due jobs using `FOR UPDATE SKIP LOCKED`.
2. The worker revalidates tenant, publication identity, canonical payload SHA-256, job schema and explicit operator approval.
3. `binario_begin_social_provider_effect(...)` is committed **before the first Meta request**.
4. The existing Meta client performs the bounded provider operation.
5. Success closes the exact lease through `binario_complete_social_publish_job(...)`.
6. Failure closes the exact lease through `binario_fail_social_publish_job(...)`.

No generic `PATCH`/replace operation is available to distributed workers.

## No-blind-retry rule

A cloud worker can crash in the narrow interval after Meta accepted a publication but before Supabase recorded the remote ID. Retrying that publication automatically could create a duplicate post.

Migration `003_social_worker_execution.sql` therefore adds `provider_started_at` and `provider_outcome_ambiguous`. An expired lease behaves differently depending on that checkpoint:

- provider effect never started: normal bounded recovery may return the job to `PENDING`;
- provider effect started: the job becomes terminal `FAILED`, is marked ambiguous, and requires manual reconciliation.

Likewise, any provider failure after the effect checkpoint is terminal. The worker deliberately favors duplicate prevention over automatic retry after an external side effect may have occurred.

## Provider scope

The core reuses the existing `MetaGraphClient` and supports the public-URL publication shapes already allowed by the remote queue:

- Facebook Page text;
- Facebook Page link;
- Facebook Page public image;
- Instagram public image;
- Instagram public Reel.

Local filesystem media and Facebook local Reel remain outside cloud execution until a separate managed cloud-media staging contract exists.

## One-shot semantics

`CloudSocialWorker.run_once()` claims a bounded number of jobs for each allowlisted tenant, processes them, returns a secret-free aggregate result and exits. It creates no daemon thread, browser endpoint or infinite polling loop.

This makes the core suitable for a later scheduler adapter such as Vercel Cron, a container scheduler or another server-side trigger without coupling provider authority to the desktop application.

## Not included yet

This increment does **not** configure a public/scheduled HTTP trigger, modify `vercel.json` with a cron cadence, provision Supabase, provision Meta credentials, upload local media to cloud storage, expose an ambiguity-resolution UI, reply to inbox messages or activate ads.

A later deployment adapter must authenticate the scheduler independently (for example a server-only cron secret), call this one-shot core, and expose only aggregate secret-free status.

## Release boundary

This is post-W99 development only. Canonical `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, Physical UAT evidence, v0.9.0 release authority and the three canonical GitHub workflows remain unchanged. This is not W100.
