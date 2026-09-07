# Post-W99 · AI Accepted Owner Handoff

## Boundary

This increment belongs only to `dev/post-w99-action-center` after the frozen W99 release candidate.

Canonical W99 remains `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` (tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`). This work does not modify `main`, does not create W100, does not authorize a release, and does not provide physical-UAT authority.

## Product gap

PR #170 made Astra recommendations reviewable and durable as `ACCEPTED` or `DISMISSED`, but an accepted recommendation had no operational continuation. It disappeared from the review queue without gaining an explicit owner, while automatically executing it would violate the product safety model.

## Contract

#171 turns a **current, explicitly accepted** recommendation into a bounded owner handoff:

1. The recommendation must still belong to the latest AI session for its exact target.
2. Its review must be `ACCEPTED` and must match the exact session id and recommendation SHA-256.
3. Owner routing uses only structured fields already present in the recommendation/session identity: `task`, `area`, `campaign_id`, `creative_media_id`.
4. The application never chooses an owner from `title`, `why` or `next_step` prose.
5. If structured identity is insufficient, the recommendation becomes `OWNER_GAP` and is shown in Astra but is not inserted into Hoy / Action Center.
6. A safe unresolved handoff enters Action Center as `source=AI_HANDOFF`, `kind=ai_accepted_handoff`, rank `87`, urgency `LOW`.
7. The handoff navigates to the canonical owner record. It does not press, submit, prefill or execute an owner control.
8. Opening the owner does not mark the handoff complete.
9. Human resolution is explicit and local: `APPLIED` or `NOT_APPLIED`.
10. `APPLIED` means only that the operator states the recommendation was applied through the owner workflow; the resolution endpoint itself performs no marketing action.
11. Repeating the same resolution is idempotent. Changing an already durable outcome conflicts.

## Owner routing

Routing is intentionally narrow and fail-closed.

### Campaign AI target

- `CAMPAIGN` or `STRATEGY` area + exact `campaign_id` → **Campaign Center**.
- `CONTENT`, `CREATIVE` or `PAID_MEDIA` area + exact `campaign_id` → **Execution Workspace**, which already owns campaign execution coordination.
- `CRM` without an exact CRM entity → `OWNER_GAP`.

### Creative AI target

- `CONTENT` or `CREATIVE` + exact `creative_media_id` → **Contenido**.
- `CAMPAIGN` or `STRATEGY` + exact `campaign_id` → **Campaign Center**.
- `PAID_MEDIA` + exact `campaign_id` → **Execution Workspace**.
- Missing exact identity → `OWNER_GAP`.

Company-level strategy or CRM prose is never translated into a guessed contact, opportunity, campaign or creative owner.

## API

- `GET /api/companies/{company_id}/ai/recommendation-handoffs`
  - local read only
  - no provider read
  - no AI generation
  - no business mutation
- `POST /api/companies/{company_id}/ai/recommendation-handoffs`
  - body: `recommendation_id`, `outcome`
  - outcome: `APPLIED | NOT_APPLIED`
  - durable local resolution only
  - recommendation/session/digest and owner eligibility are resolved server-side

The browser never submits session id, content digest, campaign id, media id or owner route as authority.

## UI

`web/ai-recommendation-handoff.js` adds:

- an Astra section for accepted recommendations pending handoff;
- explicit `OWNER_GAP` visibility;
- `Abrir módulo responsable` for safe structured routes;
- a transient owner context card after navigation;
- `Marcar aplicada` and `No aplicar`, both behind explicit confirmation.

The exact recommendation id is retained only in transient browser memory while navigating. No `localStorage`, `sessionStorage`, timers or polling are used by this layer.

## Safety

This increment does not execute recommendations. In particular it does not:

- publish content;
- activate or change paid media;
- create or mutate CRM contacts, opportunities or activities;
- create creatives or campaigns;
- call Meta;
- call an AI provider;
- click or submit an owner control;
- infer completion from navigation;
- infer an owner from AI free text.

There remain exactly three GitHub workflows:

- `ci.yml`
- `full-mac-app.yml`
- `persistent-release.yml`
