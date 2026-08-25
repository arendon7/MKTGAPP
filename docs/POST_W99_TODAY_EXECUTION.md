# Post-W99 · Today / Operator Execution

## Purpose

Today is a bounded execution surface for the selected company. Its job is to reduce cognitive load after Portfolio, Executive Cockpit and Action Center have already established context and priority.

It answers one practical question:

> **What are the next few things I should actually work on now?**

Today is not a second prioritization engine.

## Authority

Action Center remains the only cross-module priority authority for a company.

Today applies exactly one selection rule:

`FIRST_N_CANONICAL_ACTION_CENTER_ITEMS`

where `N` is between 1 and 5 and the normal product surface uses 5.

The selected rows keep their original:

- `id`;
- `rank`;
- `urgency`;
- `source`;
- `blocking` state;
- due date;
- reason/explanation;
- canonical navigation target.

Today does not re-score, sort, deduplicate, value-weight or reinterpret due dates.

## Focus labels

Focus labels are presentation-only:

- `CRITICAL` → `NOW`;
- `HIGH` → `NOW`;
- `MEDIUM` → `TODAY`;
- `LOW` → `OPTIONAL` / “Si hay tiempo”.

These labels never alter canonical order.

## Endpoint

`GET /api/companies/{company_id}/today-execution`

Schema:

`binario.marketing.today-execution.v1`

The payload contains:

- bounded `plan`;
- `primary_action`;
- counts for `NOW / TODAY / OPTIONAL`;
- number of canonical actions outside the five-item focus cap;
- minimal Executive Cockpit context;
- explicit authority and safety contracts.

## Completion model

Today deliberately has no independent “done” state and no “mark complete” mutation.

The operator opens the canonical owner module, performs the real action there and then refreshes Today. The plan is recomputed from Action Center, so an item leaves the daily focus only when the underlying canonical state has actually changed.

This prevents divergence between a cosmetic checklist and real CRM/campaign/publication state.

## UI

`web/today-execution.js` adds:

- `Hoy / Execution` navigation;
- a compact Home strip with the first action;
- a five-step ordered plan;
- urgency/source/blocking/due context;
- original Action Center explanation;
- navigation to the owner module;
- explicit overflow count and link to the full Action Center;
- a manual `Actualizar plan` action.

There is no polling.

## Safety

Today is:

- company-scoped;
- local-state only;
- GET-only;
- read-only;
- no provider read;
- no provider mutation;
- no CRM/campaign/publication mutation;
- no AI generation;
- no automatic execution;
- no background polling.

## Release boundary

This increment exists only on the post-W99 development chain. It does not modify `main`, `service.py`, `version.py`, W99 builders, the physical-UAT candidate, the `v0.9.0` tag intent or issue #113.

It is not W100, a release candidate or a production-readiness declaration.
