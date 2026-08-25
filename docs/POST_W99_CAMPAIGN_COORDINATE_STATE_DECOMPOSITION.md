# Post-W99 · Campaign Coordinate State Decomposition

## Purpose

`Campaign Coordinate State Decomposition` makes the final Wave 64 `COORDINATE` fallback explainable before any new UX or control handoff is attempted.

The layer does **not** replace `COORDINATE`, choose a different next action, or infer a mutation. W64 remains the next-action authority. The new projection only describes which canonical local lifecycle state caused the deterministic W64 cascade to fall through to `COORDINATE`.

This is intentionally a backend/read-only increment. It adds no browser adapter and the existing browser bootstrap chain remains unchanged.

## Why decomposition is required first

The Wave 64 cascade already has explicit branches for:

- terminal campaign → `COMPLETE`;
- no channels → `DEFINE_CHANNELS`;
- publication `FAILED` → `FIX_PUBLICATION`;
- no linked creative → `CREATE_CREATIVE`;
- no ready creative → `FINISH_CREATIVE`;
- empty selected organic distribution → `PREPARE_DISTRIBUTION`;
- publication `QUEUED` → `CALENDAR`;
- publication `DRAFT` → `SCHEDULE_OR_PUBLISH`;
- paid media `DRAFT` → `REVIEW_PAID`;
- planned-only channels without paid execution → `PLANNED_ONLY`;
- publication `PUBLISHED` or paid `REMOTE_PAUSED` → `REVIEW_RESULTS`.

Anything else reaches `COORDINATE`.

Treating that fallback as one owner/control would therefore be unsafe. The canonical lifecycle stores show that it currently contains a small set of materially different states.

## Canonical lifecycle ontology

### Publications

`social_store.STATUSES`:

- `DRAFT`
- `QUEUED`
- `PUBLISHING`
- `PUBLISHED`
- `FAILED`
- `CANCELLED`

`PUBLISHING` is a real transition state. On restart, interrupted publishing is recovered to `FAILED`; while it is actively present, however, W64 has no dedicated next-action branch and therefore reaches `COORDINATE`.

### Paid media

`paid_media_store.STATUSES`:

- `DRAFT`
- `REMOTE_PAUSED`
- `CANCELLED`

Wave 64 already handles `DRAFT` and `REMOTE_PAUSED`; linked `CANCELLED` plans can therefore remain inside the final fallback.

## Schema

`binario.marketing.campaign-coordinate-state.v1`

The projection contains:

- exact campaign identity;
- the untouched W64 `source_next_action`;
- diagnostic `state`;
- `route_scope`;
- observed creative/publication/paid counts;
- invariant violations;
- unknown lifecycle statuses;
- explicit authority and safety contracts.

## Diagnostic states

### `PUBLICATION_IN_FLIGHT`

At least one linked publication is canonically `PUBLISHING`, no unknown statuses exist, and no earlier W64 predicate is currently true.

This state is observational. It does not authorize retry, cancellation, refresh polling, provider read, or a new Control Handoff.

### `ONLY_CANCELLED_DISTRIBUTION_REMAINS`

All linked publication and/or paid-media objects are canonically `CANCELLED`, at least one such object exists, and no earlier W64 predicate is currently true.

The projection does not infer that the operator should recreate, retry, delete, archive, or switch channels.

### `COORDINATE_INVARIANT_DRIFT`

Wave 64 reports `COORDINATE`, but the same card simultaneously satisfies an earlier predicate in the certified Wave 64 cascade or contains an internal count inconsistency.

Examples:

- a `DRAFT` publication is visible even though W64 should have emitted `SCHEDULE_OR_PUBLISH`;
- a paid `REMOTE_PAUSED` row exists even though W64 should have emitted `REVIEW_RESULTS`;
- publication count histogram does not equal `organic.publications`;
- ready creative count exceeds total creatives.

This state has precedence over other classifications. A contradiction must be investigated, not papered over with a UI handoff.

### `UNCLASSIFIED_COORDINATION_STATE`

The fallback contains:

- a future/unknown publication or paid-media lifecycle status; or
- a known combination not covered by the certified in-flight/cancelled-only rules.

No behavior is inferred from an unknown state.

## Route scope

`route_scope` is descriptive only:

- `ORGANIC` → linked publications exist and no paid rows exist;
- `PAID` → linked paid rows exist and no publications exist;
- `MIXED` → both exist;
- `NONE` → neither exists.

It is not a channel recommendation or routing command.

## Invariant mirror

For a card whose W64 next action is `COORDINATE`, the projection checks the predicates that should have been consumed earlier:

- terminal campaign;
- missing channels;
- publication `FAILED`;
- zero linked creatives;
- linked creatives but zero ready creatives;
- selected organic route with no publication and no paid plan;
- publication `QUEUED`;
- publication `DRAFT`;
- paid `DRAFT`;
- planned-only channels, no organic selection, and no paid plan;
- publication `PUBLISHED`;
- paid `REMOTE_PAUSED`.

It also validates histogram totals for creatives, publications and paid media, plus the `ready <= total` creative invariant.

The mirror is not a second decision engine. It only detects that `COORDINATE` and the observed card disagree.

## API

New local GET-only diagnostic:

`GET /api/companies/{company_id}/campaigns/{campaign_id}/coordinate-state`

The endpoint rejects a campaign whose actual current Wave 64 next action is not `COORDINATE`. It does not synthesize a `NOT_COORDINATE` state.

## Action Center / Today

For an existing Action Center row with `kind = coordinate` and exact `campaign_id`, the layer adds:

`coordinate_state: <diagnostic payload>`

It preserves unchanged:

- row `id`;
- `kind`;
- `action`;
- rank;
- urgency;
- blocking;
- due date;
- reason;
- canonical queue order.

The same annotated row is copied into `next_action`/focus lanes when applicable. Today already deep-copies canonical Action Center rows, so it receives the same metadata without a second priority system.

## Authority split

- **W64 remains the next-action authority.**
- Action Center remains cross-module priority authority.
- This projection is diagnostic only.
- It does not rewrite `action`.
- It does not authorize Control Handoff.
- It does not create a new owner.
- Publication and paid-media stores remain lifecycle authorities.

## Safety

The layer is local and read-only:

- no provider reads;
- no provider writes;
- no business mutation;
- no AI generation;
- no automatic execution;
- no background polling;
- no forecast or causal inference.

Unknown or contradictory states fail closed.

## Composition

`service_post_w99_campaign_coordinate_state_decomposition_app` inherits `service_post_w99_campaign_creative_creation_intent_handoff_app` and becomes the terminal backend composition for `serve-dev`.

Because this increment adds no browser asset, the browser chain remains:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff`

## Frozen W99 boundary

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` / tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` remains frozen for Physical UAT issue #113.

This increment is not W100, Physical UAT PASS, release authority, publication authority, or production-ready.
