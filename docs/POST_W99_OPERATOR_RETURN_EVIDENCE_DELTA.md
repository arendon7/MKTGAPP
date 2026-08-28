# Post-W99 · Operator Return Evidence Delta

## Purpose

Today + Execution Return already answer whether an opened action still appears in the daily plan, remains elsewhere in Action Center, or no longer appears in the canonical queue. Operator Session Progress records those presence observations and Operator Current Priority Continuity can reopen a still-current primary action.

What remained invisible was a narrower question: **when the same `action_id` is still pending after the operator returns, which canonical fields actually changed between opening the action and rereading Action Center?**

Operator Return Evidence Delta answers only that before/after question. It is presentation-only and does not claim why a field changed, whether the operator caused the change, whether provider state is fresh, or whether work was completed.

## Capture contract

The snapshot is created only when a real `todayOpen(row)` occurs. It is stored in `sessionStorage`, scoped by exact `company_id`, and contains a whitelist projection rather than the Action Center row or provider payload.

Whitelisted fields:

- `source`, `kind`, `rank`, `urgency`, `blocking`, `due_at`, `reason.code`;
- canonical owner destination and entity IDs: `view`, `tab`, `entity_id`, `lead_id`, `contact_id`, `opportunity_id`, `campaign_id`, `media_id`;
- compact `owner_resolution`: `state`, `source_code`, `owner_view`, `target_kind`, `target_id`, `candidate_count`;
- compact `owner_drift`: `state`, `source_code`, `owner_view`, `expected_target_kind`.

The snapshot deliberately excludes `title`, `detail`, reason prose, provider responses, CRM records, campaign payloads, media payloads and arbitrary nested data.

## Return contract

The layer wraps the already-existing `executionReturnBackToToday` after Operator Current Priority Continuity. It performs no reread itself.

A delta is computed only when all of the following are true:

1. active company and captured snapshot company match exactly;
2. captured and returned `action_id` match exactly;
3. Execution Return produced a fresh nonempty `checked_at` different from the previous result;
4. returned state is one of the certified Execution Return states;
5. for pending states, `current_action.id` still matches the same action exactly.

The consumed snapshot is removed only after a fresh matching return result is observed.

## States

- `FIELDS_CHANGED`: the same action remains pending and at least one whitelisted field differs.
- `NO_WHITELISTED_CHANGE`: the same action remains pending and all whitelisted fields are equal.
- `ACTION_NOT_PRESENT_AFTER_REREAD`: Execution Return reported `NO_LONGER_PENDING`; there is no post-return row to compare.
- `NO_OPEN_SNAPSHOT`: no exact pre-open projection exists.
- `SNAPSHOT_SCOPE_MISMATCH`: company/action scope cannot be proven.
- `RETURN_CONTEXT_MISMATCH`: the returned result does not prove the same action and a fresh reread.
- `RETURN_STATE_UNSUPPORTED`: a future or malformed return state is not interpreted.
- `CURRENT_ACTION_SHAPE_INVALID`: a pending result does not contain the exact current row required for comparison.

Only the first three states render a user-facing comparison card. Fail-closed states create no executable behavior.

## UX

After `Volver y releer plan`, the card appears next to the existing Execution Return result.

For `FIELDS_CHANGED`, it renders direct `before → after` values for the whitelist only. For `NO_WHITELISTED_CHANGE`, it states that the observed fields stayed equal. For `ACTION_NOT_PRESENT_AFTER_REREAD`, it explicitly says that no after-row exists and therefore no field delta can be calculated.

Queue position is already described by Execution Return / Session Progress and is intentionally not treated as a business-state field here.

Closing the existing Execution Return message also removes the delta card. The layer does not open a module, click a control or select a new priority.

## Authority and safety

- frontend-only terminal; no new backend business endpoint;
- no POST/PATCH/PUT/DELETE;
- no provider read/write;
- no additional `fetch`, `opsApi`, XHR or `sendBeacon`;
- no polling;
- `sessionStorage` only for one scoped pre-open projection; no `localStorage`;
- no synthetic click, event dispatch or submit;
- no reprioritization;
- no AI authority;
- `completion_claimed=false`;
- `causal_change_claimed=false`;
- `provider_freshness_claimed=false`.

The comparison is evidence of two local canonical projections at two moments, nothing more.

## Composition

Runtime:

`Operator Return Evidence Delta → Operator Current Priority Continuity → Operator Session Progress → Campaign Execution Owner Drift Guard → Setup Readiness Owner Handoff → ...`

Browser tail:

`... → Operator Session Progress → Operator Current Priority Continuity → Operator Return Evidence Delta`

`service_post_w99_operator_return_evidence_delta_app` subclasses the Current Priority terminal and only appends `/operator-return-evidence-delta.js` when `/operator-current-priority-continuity.js` is served.

## Frozen W99 boundary

This increment belongs only to `dev/post-w99-action-center`.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` and tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` remain frozen for physical W99 UAT issue #113.

This is not W100, not Physical-UAT PASS, not a release candidate, and grants no release, publication or production authority.
