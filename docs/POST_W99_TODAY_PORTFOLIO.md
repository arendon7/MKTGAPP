# Post-W99 Today Portfolio

`Hoy` becomes the operator's default cross-company execution surface without creating a new priority engine.

## Source of truth

The browser reads `GET /api/portfolio-control-tower`. Portfolio Control Tower already composes the company-scoped Action Center queues and sorts the global queue deterministically. This increment does not re-rank, score, forecast or weight work by commercial value.

## Operator contract

- Default mode: all active companies.
- Focus cap: first five items from the existing portfolio queue.
- Every item preserves its company identity, owner action, urgency, reason and blocking state.
- Opening an item switches to the exact company before opening the owning module.
- The operator can explicitly switch to the historical single-company Today plan and return to the portfolio view.
- Refresh is explicit; there is no polling.

## Safety

The new layer is browser composition only. It adds no POST/PATCH/DELETE business route, provider read, provider mutation, CRM mutation, publication, AI generation, synthetic click or automatic execution.

## Release boundary

This is post-W99 development only. It does not modify canonical `main`, W99, `v0.9.0`, Physical UAT evidence, release authority, release workflows or release builders. It is not W100.
