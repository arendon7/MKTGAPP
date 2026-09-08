# Post-W99 · Selective Portfolio Inbox Refresh

## Purpose

Refine the explicit multi-company Inbox refresh introduced after W99 so the default operator action consults Meta only for companies whose local Inbox-attention evidence actually requires refresh.

This increment is an efficiency and operator-control refinement. It does not add a new provider-read authority, scheduler, background loop, CRM workflow, reply path, publication path, paid-media action or AI capability.

## Base authority

The provider-read authority remains the explicit route and runtime introduced by the portfolio Inbox refresh layer:

- local plan: `GET /api/portfolio/inbox-refresh-plan`
- explicit mutation boundary: `POST /api/portfolio/inbox-refresh`
- per-company provider read: existing `refresh_inbox_attention(company_id)`

The POST contract remains `{company_ids: [...]}` and still revalidates that every requested company is active and has an Inbox mapping before any provider read.

## Selective default plan

The local plan now exposes:

- `company_ids`: bounded visible configured-company list retained for the v1 contract;
- `refresh_company_ids`: bounded list of companies whose local attention projection has `refresh_required=true`;
- `summary.configured_overflow`: configured companies beyond the 50-row visible batch;
- `summary.refresh_overflow`: refresh-required companies beyond the 50-company provider-read batch.

Rows requiring refresh are sorted before CURRENT rows. This keeps the visible plan aligned with the selective batch when the portfolio is large.

## Operator experience

The Today control is now `Actualizar Inbox pendiente`.

Before any provider read the browser reloads the local plan and uses only `refresh_company_ids`. It then requires `window.confirm` with the exact number of companies that will be consulted.

When no company requires refresh, the control shows `Inbox al día` and is disabled. A CURRENT snapshot is therefore not reread merely because another brand needs refresh.

## Overflow semantics

The operation limit remains 50 companies per explicit batch.

Configured-company overflow no longer blocks a safe smaller selective batch. For example, 53 configured brands with 45 stale/missing snapshots can refresh those 45 in one explicit operation. If 53 snapshots themselves require refresh, `refresh_overflow=3` and the default control refuses a silent partial operation.

`eligible_overflow` remains in the v1 plan for backward compatibility and continues to describe configured rows beyond the visible 50-row plan. New selective logic uses `refresh_overflow`.

## Safety boundaries

The refinement preserves all #174 boundaries:

- no provider read during GET plan generation;
- no polling or background refresh;
- no automatic retry;
- no direct browser call to Meta;
- no replies or comment mutations;
- no CRM mutation;
- no social publication or paid-media mutation;
- no AI generation;
- no raw Inbox body, provider person ID, provider link or provider error text in the aggregate result;
- failures remain isolated per company;
- only the operator-triggered POST can perform provider reads.

The browser refreshes Action Center, Portfolio and Today only from local app projections after the explicit POST completes.

## Release boundary

This is post-W99 development only.

Canonical frozen W99 `main` remains:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Tree:

`53d1cf04a67da4308b37ac03c0be4546a04f36eb`

This increment has no release authority, no physical-UAT authority and makes no W100 claim. The repository continues to use exactly the three existing workflows: `ci.yml`, `full-mac-app.yml`, and `persistent-release.yml`.
