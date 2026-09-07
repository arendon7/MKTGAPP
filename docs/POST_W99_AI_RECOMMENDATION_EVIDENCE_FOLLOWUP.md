# Post-W99 · AI Recommendation Evidence Follow-up

## Purpose

This increment closes the loop after an Astra recommendation has been explicitly accepted and later marked `APPLIED` by a human operator.

`APPLIED` is only local operator evidence that the handoff was closed as applied. It does **not** prove that a provider-side, CRM, publishing, paid-media, creative, or campaign mutation occurred, and it does **not** prove that Astra caused any later result.

The follow-up layer asks a narrower question: **what evidence was observed after that human closure on the exact structured campaign or creative identity?**

## Canonical flow

`AI session → recommendation → human ACCEPTED → structured owner handoff → human APPLIED → observation window → Learning/Results snapshot → post-application evidence`

The layer never skips the human handoff and never executes the recommendation.

## Evidence states

- `OBSERVATION_WINDOW`: fewer than 24 hours have elapsed since the human `APPLIED` resolution and no later snapshot exists yet.
- `CAPTURE_DUE`: at least 24 hours have elapsed and no later Learning snapshot exists. Action Center may add one LOW-priority `AI_EVIDENCE` item to open Results and capture evidence manually.
- `EVIDENCE_AVAILABLE`: a later Learning snapshot contains observed marketing metrics on the exact structured campaign or creative target.
- `POST_SNAPSHOT_NO_TARGET_SIGNAL`: a later snapshot exists, but it contains no observed metrics for that exact target.
- `IDENTITY_GAP`: the historical AI session/recommendation needed to reconstruct the exact target is no longer available. The layer fails closed rather than inferring from prose.
- `INVALID_APPLIED_TIME`: chronology cannot be ordered safely.

`NOT_APPLIED` handoffs do not enter post-application tracking.

## Historical identity

A recommendation remains observable after Astra creates a newer session for the same target. The implementation reconstructs each historical recommendation from its retained `AISession` using the canonical recommendation ID/digest logic and matches the durable handoff resolution by:

- company
- recommendation ID
- session ID
- recommendation SHA-256

No owner or evidence target is inferred from the recommendation title, rationale, or next-step prose.

## Exact evidence target

- `CREATIVE` recommendation with an exact `creative_media_id` → evidence is matched by that media ID.
- campaign recommendation with an exact `campaign_id` → evidence is matched by that campaign ID.

A snapshot for another campaign or another creative does not satisfy the follow-up.

## No causal inference

Post-application evidence is observational. A metric appearing after `APPLIED` **no demuestra causalidad** and is not labelled as an uplift, improvement, degradation, ROI impact, or Astra-attributed result.

The browser surface states this explicitly. `learning_payload` also exposes `ai_recommendation_causal_attribution: false`.

## Action Center deduplication

The follow-up can add only an overdue capture task, rank `88`, urgency `LOW`, source `AI_EVIDENCE`.

If the canonical campaign Results flow already exposes `CAMPAIGN_CAPTURE_RESULTS` for the same campaign, the Astra follow-up is shadowed and does not create a duplicate task.

## Provider and execution boundary

The projection and browser surface are read-only:

- no provider read
- no provider mutation
- no AI generation
- no CRM mutation
- no publishing
- no paid-media activation
- no content generation
- no automatic Learning refresh
- no polling/timers
- no browser persistence

The only browser action is navigation to the canonical Results surface, where the operator may explicitly refresh results using existing controls.

## HTTP surface

`GET /api/companies/{company_id}/ai/recommendation-evidence`

There is no POST endpoint in this increment.

## Learning integration

`learning_payload()` gains `ai_recommendation_followup`, containing the local projection summary and tracked recommendations. Existing provider refresh and decision authority remain unchanged.

## macOS development bundle

The isolated post-W99 development bundle requires:

- `ai_recommendation_evidence.py`
- `service_post_w99_ai_recommendation_evidence_app.py`
- `web/ai-recommendation-evidence.js`

The development bundle still has:

- `release_authority: false`
- `physical_uat_authority: false`
- `w100: false`

## Frozen release boundary

Canonical W99 `main` remains frozen at:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

This post-W99 increment does not modify `main`, does not certify physical UAT, and does not create a release.

## Workflow guard

The repository continues to use exactly the existing three workflows:

1. `ci.yml`
2. `full-mac-app.yml`
3. `persistent-release.yml`

No fourth workflow is introduced.
