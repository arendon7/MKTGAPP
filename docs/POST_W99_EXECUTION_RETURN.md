# Post-W99 · Execution Return Flow

## Purpose

Today reduces a company’s canonical Action Center queue to a maximum of five actions. The next product problem is navigation continuity: after the operator opens one of those actions in CRM, campaigns, calendar, content or another owner module, the app should make it obvious how to return to the daily plan without inventing a second completion state.

Execution Return Flow closes that loop.

It answers:

> **I opened an action from Today, worked in the owner module, and now I want to return to the plan with the same context. What changed?**

## Authority boundary

Execution Return is navigation context only.

It is not:

- a task database;
- an audit trail;
- evidence that work happened;
- a completion checkbox;
- a priority engine;
- a workflow orchestrator.

Action Center remains priority authority. The owner module remains completion authority.

## Session context

When an operator opens an action from Today, `web/execution-return.js` stores a deliberately small browser-session snapshot under:

`binario.marketing.execution-return.v1`

The snapshot contains only what is required to restore navigation:

- `company_id`;
- canonical `action_id`;
- title/source/urgency for UI context;
- previous Today sequence and visible-plan count;
- the canonical action destination (`view`, `tab` and entity identifiers);
- `opened_at`.

It uses `sessionStorage`, not backend persistence. It is scoped to the browser tab/session and is discarded when the user exits the flow or when the tab session ends.

The stored context never changes CRM, campaign, publication, media or decision state.

## Owner-module ribbon

After Today opens the canonical destination, a floating ribbon remains visible across both:

- Marketing Operations shell views; and
- the legacy Content shell.

The ribbon shows:

- that the operator arrived from Today;
- the original action title;
- previous sequence position;
- source and urgency;
- **Continuar acción**;
- **Volver y releer plan**;
- **Salir del recorrido**.

`Continuar acción` reconstructs only the canonical navigation target and delegates back to `actionCenterOpen`; it does not execute the underlying business action.

## Return semantics

`Volver y releer plan` performs local GET projections only:

1. restore the original company selection if it still exists;
2. reload the full Action Center;
3. reload Today;
4. locate the original canonical `action_id`;
5. classify its current visibility;
6. clear the active navigation session;
7. return to Today with an explanatory result.

The result has three UI states:

### `STILL_IN_TODAY`

The action still exists in Action Center and remains inside Today’s top five. The UI shows its current Today sequence.

### `STILL_PENDING`

The action still exists in Action Center but no longer fits inside Today’s five-item focus cap. The UI reports its full canonical queue position when available.

### `NO_LONGER_PENDING`

The action ID is no longer present in the current Action Center queue.

This state deliberately does **not** claim that the task was completed. Its disappearance may reflect any canonical state transition that removes it from Action Center. The operator is simply told that it is no longer pending in that queue and can continue with the current priority.

## Why there is no “completed” claim

Navigation state cannot prove business execution.

For example, a campaign action may disappear because the campaign changed state; a CRM follow-up may disappear because it was rescheduled; a publication issue may disappear after the publication state changed. The correct authority is the owner module and the resulting canonical projections, not a browser-local flag.

Therefore Execution Return never stores `done=true`, never writes completion state and never interprets absence as proof of success.

## Company isolation

A return context is bound to one `company_id`.

The ribbon is only surfaced while the selected company matches that context. If the operator explicitly chooses to return, the original company is restored only if that company still exists in the already loaded local company list.

If the company no longer exists, the navigation context is discarded without mutating anything.

## Reload/resume behavior

Because the context is stored in `sessionStorage`, it can survive ordinary navigation and a same-tab page reload. The ribbon offers **Continuar acción** to reopen the stored canonical destination or **Volver y releer plan** to abandon the destination and recompute Today.

No background polling is used.

## Runtime composition

`service_post_w99_execution_return_app` inherits `service_post_w99_today_execution_app`.

It does not add a business endpoint. It only:

- serves `/execution-return.js`;
- appends its bootstrap after `/today-execution.js`;
- preserves every prior post-W99 API and UI surface.

The development chain remains:

Portfolio Control Tower → Executive Marketing Cockpit → Today / Operator Execution → Execution Return Flow.

Action Center remains underneath as the canonical cross-module priority authority.

## Safety contract

Execution Return is:

- company-scoped navigation context;
- browser-session only;
- no backend persistence;
- no provider read;
- no provider write;
- no CRM/campaign/publication mutation;
- no AI generation;
- no automatic execution;
- no automatic completion;
- no background polling;
- no causal or success inference.

The only re-check on return is through existing local read projections.

## Release boundary

This increment exists only on the post-W99 development chain.

It does not modify:

- `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`;
- `service.py`;
- `version.py`;
- W99 builders or workflows;
- the frozen physical-UAT candidate;
- the `v0.9.0` tag intent;
- issue #113.

It is not W100, a release candidate or a production-readiness declaration.
