# Post-W99 · Campaign Execution Owner Relay

## Purpose

Campaign Execution Owner Relay closes the remaining identity gaps between the deterministic next action produced by Wave 64 and the canonical module that actually owns that work.

It does **not** create a new campaign, publication, creative, paid-media or execution mutation. It resolves existing local IDs and improves navigation only when a unique owner can be proven.

The layer inherits Campaign Results Owner Handoff and therefore remains inside `serve-dev`; canonical `serve` is unchanged.

## Why this layer exists

Wave 64 already decides the next execution step for each campaign. Most routes were already structurally exact:

- `DEFINE_CHANNELS` → campaign;
- `FINISH_CREATIVE` → `media_id`;
- `PREPARE_DISTRIBUTION` → `media_id`;
- `PLANNED_ONLY` / `COMPLETE` → campaign;
- `REVIEW_RESULTS` → campaign results.

The audit found four real identity gaps:

1. Results Intelligence emits `FIX_EXECUTION` and sends the user to the exact W64 campaign, while W64 then emits `FIX_PUBLICATION` without a publication ID.
2. `SCHEDULE_OR_PUBLISH` and `CALENDAR` know the campaign but not which publication row is the final owner.
3. `REVIEW_PAID` knows the campaign but not which local paid-media draft owns the action.
4. Contextual Deep Linking still annotated Wave 34 `.company-content-card` nodes for `MEDIA`, while the default visible owner is now Wave 49 Creative Studio `.w49-item`; a valid `media_id` could therefore fail to highlight the exact current UI.

## Exact local owner context

New read-only endpoint:

`GET /api/companies/{company_id}/campaigns/{campaign_id}/execution-owner-context`

The endpoint:

- validates the campaign with the canonical Campaign Store;
- reads Wave 64 `campaign_execution_workspace` as next-action authority;
- rebuilds only the canonical local links already used by W64 between campaign, Creative Studio, publications and paid-media plans;
- never reads a provider;
- never writes business state;
- never generates AI output.

Schema:

`binario.marketing.campaign-execution-owner-context.v1`

## Resolution states

### `EXACT_TARGET`

A canonical final ID is uniquely proven. Only this state may improve the Action Center route.

### `AMBIGUOUS_TARGET`

More than one canonical object satisfies the W64 condition. The relay returns the candidates for explanation but chooses none.

Examples:

- two FAILED publications;
- two DRAFT publications;
- two DRAFT paid-media plans.

### `OWNER_ONLY`

The owner module is known, but the work represents creation/coordination rather than one existing object.

Examples:

- `CREATE_CREATIVE`;
- `COORDINATE`;
- broad calendar review when no unique queued publication exists.

### `NO_TARGET`

W64 reports a condition that should have a target, but the current canonical local read no longer contains one. The original owner route is preserved; no substitute is inferred.

## Mapping rules

| W64 code | Exact rule | Final owner |
|---|---|---|
| `DEFINE_CHANNELS` | campaign ID itself | Wave 35 campaign |
| `FIX_PUBLICATION` | exactly one linked `FAILED` publication | Wave 42 publication |
| `FINISH_CREATIVE` | W64 `media_id` appears exactly once among linked creatives | Wave 49 media |
| `PREPARE_DISTRIBUTION` | W64 `media_id` appears exactly once among linked creatives | Wave 49 media |
| `SCHEDULE_OR_PUBLISH` | exactly one linked `DRAFT` publication | Wave 42 publication |
| `CALENDAR` | exactly one linked `QUEUED` publication; otherwise owner-only/ambiguous | Wave 42 publication/calendar |
| `REVIEW_PAID` | exactly one linked paid-media `DRAFT` | Wave 48 paid draft |
| `PLANNED_ONLY` / `COMPLETE` | campaign ID itself | Wave 35 campaign |
| `REVIEW_RESULTS` | campaign ID itself | Campaign Results Owner Handoff |
| `CREATE_CREATIVE` / `COORDINATE` | no existing unique object is implied | owner only |

No rule uses title, copy, date proximity, channel preference, DOM position, fuzzy matching or AI.

## Action Center behavior

The layer preserves the Action Center row identity and priority contract.

For a row carrying a campaign-derived execution action:

1. read the exact campaign execution owner context;
2. attach `owner_resolution`;
3. if and only if the state is `EXACT_TARGET`, update the action's owner identifiers;
4. preserve `id`, `kind`, `rank`, `urgency`, `due_at`, `blocking`, reason and queue order.

Examples:

- `fix_execution` + one FAILED publication becomes `calendar + entity_id=<publication_id>` while the action remains `fix_execution`;
- `review_paid` + one DRAFT becomes `pauta + entity_id=<draft_id>`;
- two FAILED publications remain on the exact W64 campaign with `AMBIGUOUS_TARGET` and no guessed publication.

## Browser exactness repair

### Wave 49

When the target kind is `MEDIA`:

- force the already-existing W49 pipeline tab;
- set `wave49CreativeState.selectedId` to the canonical `media_id` before render;
- annotate `.w49-item` only when DOM cardinality equals the W49 local item list;
- locate exactly one matching `data-deep-media-id`.

The layer does not edit the creative.

### Wave 48

For `PAID_DRAFT`:

- use the already-loaded `wave47State.paidMedia` rows;
- mirror Wave48's visible reverse ordering;
- annotate `.wave48-plan` only when row count and DOM count are equal;
- locate exactly one matching draft ID.

The layer does not create Meta objects, cancel drafts or query observability.

## Control Handoff

Existing owner controls remain authoritative:

- `fix_execution`, `schedule_or_publish`, `calendar` + exact publication → Wave42 editorial panel;
- `finish_creative` + exact media → W49 creative form;
- `prepare_distribution` + exact media → W49 distribution control group; the user chooses Facebook, Instagram or Pauta;
- `define_channels` + exact campaign → W35 campaign form;
- `review_paid` + exact draft → W48 plan card/control group.

No control is clicked automatically.

If `fix_execution` is `AMBIGUOUS_TARGET` or `NO_TARGET`, Contextual Control Handoff reports an owner gap instead of presenting the generic W64 `Ir` as if it were an exact final control.

## Safety

This layer adds no:

- POST/PATCH/PUT/DELETE business route;
- provider read;
- provider mutation;
- publication;
- paid activation;
- creative save;
- campaign save;
- AI generation;
- synthetic `.click()`;
- `dispatchEvent()`;
- polling;
- fuzzy matching;
- automatic execution.

Provider-capable operations remain behind their existing human controls and confirmations. Wave48 continues to create remote objects only in `PAUSED` under its existing contract.

## Composition

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay`

## Frozen W99 boundary

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` / tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` remains frozen for physical UAT issue #113.

This post-W99 increment is not W100, is not a release candidate, does not constitute physical UAT, does not authorize publication and does not establish production readiness.
