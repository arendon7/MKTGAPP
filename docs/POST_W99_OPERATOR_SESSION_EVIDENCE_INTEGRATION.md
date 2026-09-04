# Post-W99 · Operator Session Evidence Integration

## Purpose

PR #150 stores company-scoped `ACTION_OPENED` and `RETURN_OBSERVED` events in browser `sessionStorage`. PR #152 computes a whitelisted before/after `return_evidence_delta` only after the existing Execution Return reread has completed.

Because Session Progress records the return inside an earlier wrapper, the #152 delta is created after the matching `RETURN_OBSERVED` event has already been persisted. The immediate delta card is therefore transient and the session history does not retain even a compact indication of that evidence.

This layer closes only that presentation gap. It does not create business state, infer completion, infer causal workflow progression, or make another read.

## Exact integration contract

The adapter runs after `operator-return-evidence-delta.js` and inspects the already-produced `postW99ExecutionReturnState.lastResult`.

A delta can be integrated only when all of the following are true:

1. exact `company_id`, `action_id` and non-empty `checked_at` match the return context;
2. the delta state is one of:
   - `FIELDS_CHANGED`
   - `NO_WHITELISTED_CHANGE`
   - `ACTION_NOT_PRESENT_AFTER_REREAD`;
3. `operatorSessionProgressRead(company_id)` contains exactly one `RETURN_OBSERVED` event with the same `action_id + checked_at`;
4. for `FIELDS_CHANGED`, every changed field belongs to the #152 whitelist and is unique;
5. for the two zero-delta states, the changed-field list is empty;
6. the write is reread and the compact evidence must validate exactly before the integration is reported as successful.

Any missing, duplicate, malformed, stale or unsupported shape fails closed and does not create another event.

## What is stored

Only a compact child object on the already-existing session event:

- schema `binario.marketing.operator-session-evidence-integration.v1`;
- delta `state`;
- `change_count`;
- `changed_fields` containing field names only;
- exact `checked_at`;
- `completion_claimed=false`;
- `causal_change_claimed=false`;
- `provider_freshness_claimed=false`.

The integration deliberately does **not** persist #152 `before` or `after` values, full Action Center rows, provider payloads, business payloads, title/detail prose, or another snapshot.

## UX

The existing Operator Session Progress history remains the owner of session presentation. This layer extends only its event-detail formatter:

- `FIELDS_CHANGED` reports the compact count and up to four whitelisted field labels;
- `NO_WHITELISTED_CHANGE` reports that the whitelist remained equal;
- `ACTION_NOT_PRESENT_AFTER_REREAD` records that no after-row existed for comparison.

The wording remains observational. “Action ID no longer present” still does not mean completed.

## Safety

- frontend-only terminal;
- no new business endpoint;
- no POST/PATCH/PUT/DELETE;
- no `fetch`, `opsApi`, XHR, `sendBeacon` or provider IO;
- no new storage key: reuses the existing company-scoped Session Progress record;
- no `localStorage`;
- no polling;
- no synthetic click, event dispatch or submit;
- no priority mutation or reprioritization;
- no AI authority;
- no completion or causal-successor claim;
- corrupted local evidence is ignored unless it passes the same sanitizer used for newly integrated evidence.

## Composition

Runtime tail:

`Operator Session Evidence Integration → Operator Return Evidence Delta → Operator Current Priority Continuity → Operator Session Progress → Campaign Execution Owner Drift Guard → Setup Readiness Owner Handoff → ...`

Browser tail:

`... → Operator Session Progress → Operator Current Priority Continuity → Operator Return Evidence Delta → Operator Session Evidence Integration`

`serve-dev` advances to `service_post_w99_operator_session_evidence_integration_app`. Canonical `serve` remains unchanged.

## Frozen W99 boundary

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` / tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` remains frozen for physical W99 UAT issue #113.

No es W100, no es Physical-UAT PASS, no autoriza `v0.9.0`, publicación, release ni producción.
