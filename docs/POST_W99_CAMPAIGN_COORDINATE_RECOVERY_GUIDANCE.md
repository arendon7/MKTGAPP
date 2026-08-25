# Post-W99 · Campaign Coordinate Recovery Guidance

## Purpose

Campaign Coordinate State Decomposition intentionally stopped at diagnosis. This increment adds a narrow recovery-guidance layer for the two deterministic residual states that can be explained without changing Wave 64 authority:

- `PUBLICATION_IN_FLIGHT`
- `ONLY_CANCELLED_DISTRIBUTION_REMAINS`

The layer does not invent a new next action. W64 remains the next-action authority. It only refines navigation after the existing `COORDINATE` action when a final owner can be proven from exact local IDs and canonical lineage.

## Ownership rules

### Publication in flight

When exactly one linked publication is canonically `PUBLISHING`, the action can navigate to that exact `publication_id` in Calendar/Editorial. This is observation only. No retry, forced completion, cancellation, provider refresh, or state mutation is authorized by this layer.

If two or more linked publications are `PUBLISHING`, the result is `AMBIGUOUS_EXISTING_OWNER`; all canonical candidates can be exposed diagnostically, but none is selected automatically.

If the diagnostic says `PUBLICATION_IN_FLIGHT` but the exact linked objects no longer contain a PUBLISHING publication, the resolver returns `RECOVERY_INVARIANT_GAP` and fails closed.

### Cancelled distribution

`ONLY_CANCELLED_DISTRIBUTION_REMAINS` never means that a cancelled object can be restarted. Cancelled objects stay terminal.

Recovery is modeled as creation of a new distribution route from the exact source creative. The source is resolved only through canonical lineage already owned by `CreativeStore`:

- `publication_ids` link publications to managed media.
- `paid_media_ids` link paid drafts to managed media.
- a paid plan may additionally expose its canonical `company_media_id`.

No title, copy, channel-name similarity, date proximity, fuzzy matching, or list position is used to infer ownership.

The source creative must also remain in the W64-ready stage set: `READY`, `SCHEDULED`, `PUBLISHED`, or `PAID`.

If every cancelled object resolves to the same source `media_id`, the action may navigate to that exact W49 Creative Studio item. The browser adapter can then point to an existing human-owned control only when the route is unambiguous:

- cancelled Facebook route → `Preparar Facebook`
- cancelled Instagram route → `Preparar Instagram`
- cancelled paid route from an image → `Enviar a Pauta`

Those controls remain Wave49/W48 owners. They are not invoked by the adapter.

If the lineage leads to multiple creatives, lineage is missing, the source is not W64-ready, or paid recovery resolves to a non-image media type, the resolver fails closed.

When one source media has more than one valid new distribution route, the owner can be exact while the control remains intentionally ambiguous. The UI must show that a human choice is required and must not preselect a channel.

## Backend contract

`service_post_w99_campaign_coordinate_recovery_guidance_app` inherits Campaign Coordinate State Decomposition and adds:

- `campaign_coordinate_recovery_guidance(company_id, campaign_id)`
- GET-only `GET /api/companies/{company_id}/campaigns/{campaign_id}/coordinate-recovery-guidance`
- Action Center annotation `coordinate_recovery`
- navigation refinement only when the resolver returns `EXACT_EXISTING_OWNER` or `EXACT_RECOVERY_OWNER`

The original `coordinate_state` remains intact. `kind`, rank, urgency, blocking, reason, queue order and W64 source semantics remain unchanged.

No `POST`, `PATCH`, `PUT` or `DELETE` handler is introduced.

## Browser contract

`web/campaign-coordinate-recovery-guidance.js` is zero-transport. It does not call `opsApi`, `fetch`, provider APIs, timers, synthetic clicks or mutation endpoints.

It extends existing Contextual Deep Linking and Contextual Control Handoff only after the backend has already proven an exact canonical target.

For `PUBLICATION_IN_FLIGHT`, it explicitly reports an owner gap for mutation: the publication can be inspected, but Coordinate Recovery Guidance authorizes no control.

For cancelled distribution, it can highlight one existing W49 control if and only if the expected recovery route is singular and available. Multiple valid routes remain `CONTROL_AMBIGUOUS` and require human choice.

## Safety invariants

- W64 remains the next-action authority.
- Campaign Coordinate State Decomposition remains the source of residual-state classification.
- Existing Wave42/W47/W48/W49 mutation authority is preserved.
- Exact navigation requires canonical IDs and canonical lineage.
- cancelled objects stay terminal and are never resurrected.
- Recovery never triggers provider reads, provider writes, publish, paid activation or background polling.
- Ambiguous owners and ambiguous controls fail closed.
- Guidance never reprioritizes Action Center.

## Frozen release boundary

This is development-only work on `dev/post-w99-action-center` and `serve-dev`.

Canonical `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, W99, the physical Apple Silicon candidate, intended `v0.9.0` tag and issue #113 UAT gate remain unchanged. This increment is not W100, not a release candidate and not publication authority.
