# Post-W99 · Portfolio Inbox Refresh

## Purpose

This increment removes a repetitive operator step from the multi-company workflow. From **Hoy**, one explicit action can refresh Inbox attention snapshots for the configured companies without entering each company individually.

It is a convenience layer over the already-existing single-company `refresh_inbox_attention()` authority. It does not introduce a second Inbox reader or a background scheduler.

## Flow

`Hoy multiempresa → local refresh plan → operator confirmation → exact company_ids POST → sequential existing Inbox refresh → minimized local snapshots → local Portfolio/Today projection refresh`

The plan GET never reads Meta. Provider reads occur only after the operator confirms the batch POST.

## Local plan

`GET /api/portfolio/inbox-refresh-plan`

The plan:

- reads active companies locally;
- includes only companies with Facebook or Instagram mapping;
- reads existing minimized Inbox attention state locally;
- exposes whether each snapshot is `CURRENT`, `MISSING`, `STALE`, anomalous or locally unreadable;
- returns channel configuration booleans, never Facebook Page IDs or Instagram IDs;
- performs no provider call.

A corrupt local snapshot becomes `LOCAL_STATE_ERROR`; it does not trigger an automatic provider read.

## Explicit batch refresh

`POST /api/portfolio/inbox-refresh`

Payload:

```json
{"company_ids":["company_..."]}
```

Rules:

- `company_ids` is required and non-empty;
- IDs must be unique and valid;
- maximum 50 companies per operation;
- every ID is revalidated server-side as an active company with Inbox mapping;
- invalid/unmapped input fails before any provider read;
- reads run sequentially using the existing single-company Inbox refresh function;
- there is no automatic retry;
- one company failure does not abort later companies.

## Response minimization

The cross-company result contains only:

- internal company ID/name;
- `REFRESHED` or `FAILED`;
- snapshot capture timestamp for successful refreshes;
- minimized attention-candidate count;
- aggregate requested/refreshed/failed counts.

It does not return:

- conversations;
- comments;
- message bodies;
- provider person IDs;
- provider links;
- raw provider error text;
- access tokens or other credentials.

The existing per-company minimized snapshot remains the only durable Inbox attention evidence.

## Browser behavior

`web/portfolio-inbox-refresh.js` adds **Actualizar Inbox de todas** to Hoy multiempresa.

Before the POST it shows `window.confirm` explaining that the operation will read Meta for the exact planned companies and will not reply, comment, modify CRM, publish or generate AI.

After completion the browser reloads only local projections so the new snapshots can flow through:

`Inbox attention → Action Center → Portfolio Control Tower → Hoy`.

The adapter uses **sin polling**, timers, MutationObserver, background refresh or direct provider/browser calls.

If the configured-company population exceeds the batch limit, the UI refuses to execute a silent partial batch.

## Authority boundaries

This increment can perform only the already-authorized provider reads caused by the explicit batch POST. It cannot:

- send Messenger replies;
- post Instagram replies/comments;
- create or modify CRM records;
- publish content;
- activate paid media;
- generate AI;
- install a scheduler;
- retry automatically.

## Failure isolation

Each requested company is attempted once, in the exact operator-confirmed order. Provider failures are reduced to a generic `FAILED` state in the cross-company response so provider text or remote identities cannot leak across company boundaries.

## macOS development boundary

The post-W99 development app remains isolated from the canonical release and retains:

- `release_authority: false`
- `physical_uat_authority: false`
- `w100: false`

## Frozen release boundary

Canonical W99 `main` remains:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

This increment does not modify `main`, certify physical UAT or create a release.

## Workflow guard

The repository continues to use exactly:

1. `ci.yml`
2. `full-mac-app.yml`
3. `persistent-release.yml`

No fourth workflow is introduced.
