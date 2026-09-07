# Post-W99 · AI Recommendation Review

## Boundary

This increment belongs only to `dev/post-w99-action-center` after the frozen W99 release candidate.

Canonical W99 remains `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` (tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`). This work does not modify `main`, does not create W100, does not authorize a release, and does not provide physical-UAT authority.

## Product gap

Wave 51 and Wave 65 already generate and persist optional AI analysis, but recommendations were only historical/display data. They could not become an explicit human-review item in Hoy / Action Center, and there was no durable ACCEPTED / DISMISSED review state.

## Contract

The increment adds a local review layer over AI sessions that already exist:

1. Only the latest AI session for each exact target is eligible: STRATEGY/company, CAMPAIGN/campaign ID, or CREATIVE/media ID.
2. At most five normalized recommendations per current session are projected.
3. Every recommendation receives a deterministic ID and SHA-256 from its normalized content.
4. Action Center receives **one LOW-priority review task per AI session**, never one task per recommendation.
5. The priority written by the AI (`HIGH`, `MEDIUM`, `LOW`) is context only. It never changes Action Center rank or urgency.
6. When a current campaign AI session has recommendations pending review, the older `OPTIONAL_AI` campaign action is suppressed to avoid duplicate work.
7. The browser may submit only `recommendation_id` plus `ACCEPTED` or `DISMISSED`. Session ID and content digest are resolved and verified server-side.
8. An unreviewed recommendation from a superseded AI session is rejected fail-closed.
9. Repeating the same review decision is idempotent. Attempting to change an already durable decision conflicts.
10. ACCEPTED means only “human reviewed and accepted as a recommendation”. It does **not** execute the recommendation.

## API

- `GET /api/companies/{company_id}/ai/recommendation-review`
  - local read only
  - no AI generation
  - no provider read
  - no business mutation
- `POST /api/companies/{company_id}/ai/recommendation-review`
  - body: `recommendation_id`, `decision`
  - decision: `ACCEPTED | DISMISSED`
  - durable local review only
  - no provider call
  - no marketing execution

## Hoy / Action Center

A pending AI session is projected as `source=AI_REVIEW`, `kind=ai_recommendation_review`, rank `86`, urgency `LOW`.

The action deep-links to `Resultados & IA` with the exact `session_id` kept only in transient browser memory. The adapter also wraps Portfolio navigation so multi-company Hoy first selects the owning company and then focuses the exact AI session.

No `localStorage`, `sessionStorage`, timers, polling, MutationObserver or external provider fetch is added for this handoff.

## Human review UI

`web/ai-recommendation-review.js` adds a review section inside Resultados & IA. Each current recommendation shows:

- title
- explanation
- AI-suggested priority, explicitly marked non-authoritative
- area
- proposed next step
- `Aceptar recomendación`
- `Descartar`

Both mutations require an explicit click and confirmation. After review, Action Center, Portfolio and Today are refreshed only from local application endpoints.

## Safety

This increment does not execute recommendations. In particular it does not:

- publish organic content
- activate or change paid media
- create or mutate CRM contacts, opportunities or activities
- create creatives or campaigns
- call Meta
- call an AI provider while reading or reviewing
- auto-accept or auto-dismiss recommendations
- turn AI-provided priority into system priority

There remain exactly three GitHub workflows:

- `ci.yml`
- `full-mac-app.yml`
- `persistent-release.yml`
