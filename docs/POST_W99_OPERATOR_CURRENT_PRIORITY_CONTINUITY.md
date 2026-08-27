# Post-W99 · Operator Current Priority Continuity

## Purpose

Operator Session Progress (#150) records the exact `next_action_id` returned by Execution Return when an opened action becomes `NO_LONGER_PENDING`, but its panel intentionally does not use that identity. This layer closes that UX gap without inventing causal progression.

It answers only: **is the priority that was primary in that canonical reread still exactly the primary Today action now?**

It never answers: “did the previous action complete?” or “is this the causal successor?”.

## Source truth

Execution Return rereads Action Center and Today after explicit human return. When the original `action_id` no longer exists, it stores `next_action = todayPayload.primary_action`.

Operator Session Progress stores only that returned `next_action_id` in the company-scoped session event. This layer reads the already-sanitized session evidence and the currently loaded Today payload. It creates no new persistent evidence.

## Exact states

- `CURRENT_PRIORITY_CONFIRMED` — latest return is `NO_LONGER_PENDING`; its `next_action_id` appears exactly once in current Today `plan`; it is also `primary_action.id`, `status.primary_action_id`, plan position 1, operator sequence 1, and has a non-empty owner `action.view`.
- `PLAN_CLEAR_AFTER_RETURN` — the return had no next priority and the current Today plan remains empty.
- `OBSERVED_PRIORITY_NO_LONGER_PRIMARY` — the recorded priority still appears but is no longer canonical position 1.
- `OBSERVED_PRIORITY_NO_LONGER_IN_TODAY` — the recorded priority is no longer in the current Today focus.
- `RETURN_PRIORITY_MISSING` — the event has no `next_action_id` while Today now has a primary action; continuity cannot be proven.
- `CURRENT_PLAN_AMBIGUOUS` — duplicate current plan identity; fail closed.
- `CURRENT_PRIORITY_SHAPE_INVALID` — identity matches but owner/sequence shape is not the certified Today shape; fail closed.
- `TODAY_NOT_READY`, `NO_RETURN_EVIDENCE`, `NO_HANDOFF_REQUIRED`, `NO_COMPANY` — no eligible handoff is rendered.

## Human handoff

Only `CURRENT_PRIORITY_CONFIRMED` renders **Abrir prioridad actual**.

The button performs a second full local identity check at the moment of the human click. Only if the same action remains the exact primary Today row does the existing `todayOpen(candidate)` navigation run. `todayOpen` remains the owner of execution-context capture and all downstream handoffs.

If the plan changed between render and click, the adapter refuses navigation and asks the operator to reread the current plan.

## No causal or completion inference

`next_action_id` means only “the action that Today reported as primary in that reread”. It is not evidence that:

- the previous action completed;
- the new action was caused by the previous action;
- the new action is a workflow successor;
- any business mutation succeeded.

All completion/business truth remains in canonical owner stores and Action Center.

## Composition

Runtime:

`Operator Current Priority Continuity → Operator Session Progress → Campaign Execution Owner Drift Guard → Setup Readiness Owner Handoff → ...`

Browser tail:

`... → Setup Readiness Owner Handoff → Campaign Execution Owner Drift Guard → Operator Session Progress → Operator Current Priority Continuity`

The new service only appends `/operator-current-priority-continuity.js` when the certified `/operator-session-progress.js` asset is served.

## Safety

- no new business endpoint;
- no POST/PATCH/PUT/DELETE;
- no provider read/write;
- no `fetch`, `opsApi`, XHR, sendBeacon or polling;
- no localStorage or new sessionStorage write;
- no synthetic click/event/submit;
- no reprioritization;
- no AI authority;
- no completion inference;
- no causal-successor inference;
- a human click may call the existing `todayOpen` only after exact fresh revalidation.

## Frozen W99 boundary

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` / tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` remains frozen for physical W99 UAT issue #113.

This increment is development-only on `serve-dev`. It is not W100, not Physical-UAT PASS, not a release candidate, and grants no release/publication/production authority.
