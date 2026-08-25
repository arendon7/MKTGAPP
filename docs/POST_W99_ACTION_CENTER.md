# Post-W99 · Action Center

## Boundary

This work lives only on `dev/post-w99-action-center`, branched from frozen `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`.

- It **NO modifica `main`**.
- It does not rebuild or replace the W99 physical-UAT candidate.
- It does not create or imply release authority, publication authority or production readiness.
- **NO se crea W100** while issue #113 remains the physical-UAT gate.
- `v0.9.0` remains a prepared tag intent, not a publication performed by this branch.

## Product problem

The certified product already computes local next actions in Daily Workdesk, Commercial Desk, Campaign Execution and Results Intelligence. The operator still has to visit those surfaces separately to discover the globally most important item.

## Increment

`Action Center` adds a single company-scoped, explainable priority queue over those existing projections.

Order of attention:

1. blocking operational failures and overdue work;
2. unresolved lead identity and incomplete CRM handoffs;
3. current-day operational work;
4. campaign execution/results decisions;
5. setup/product gaps;
6. optional/low-urgency review.

The Action Center does not become the owner of business mutations. Its buttons deep-link to the canonical module that already owns each action.

## API

`GET /api/companies/{company_id}/action-center`

Schema: `binario.marketing.action-center.v1`.

The response contains `next_action`, urgency/source summaries, `focus.now|next|later`, the normalized explainable queue, contracts and explicit safety flags.

## UI

`web/action-center.js` adds `Prioridades / Action Center`, a global-priority strip on Home, source/urgency filters, explanation per recommendation and navigation-only actions into canonical modules.

## Safety contract

The increment is intentionally GET-only: no provider reads/writes, no CRM/campaign/publication mutation, no AI generation, no silent execution, no background polling and no cloud dependency.

Physical UAT for W99 remains independently executable later against the exact frozen artifact because this branch does not mutate the frozen candidate or `main`.
