# Post-W99 · AI Human Feedback Context

## Purpose

This increment lets an explicit Astra generation see a small amount of prior **human-reviewed recommendation history** for the exact same AI target.

The goal is continuity, not autonomous memory and not self-validation. Astra may use prior operator decisions to avoid mechanically repeating rejected ideas, but those decisions are not performance scores and do not authorize any action.

## Canonical flow

`Astra session → recommendation → human review → optional owner handoff → optional human APPLIED/NOT_APPLIED closure → optional observational evidence → later explicit Astra request`

Only the final explicit Astra request causes a provider call. There is no background generation.

## Exact target scope

Feedback is included only when the historical AI target exactly matches the new request:

- `STRATEGY` → company strategy target
- `CAMPAIGN` → same exact `campaign_id`
- `CREATIVE` → same exact `creative_media_id` and target tuple

Feedback from another campaign or creative is not blended into the request.

## Human review required

A historical recommendation becomes feedback only after an operator explicitly records:

- `ACCEPTED`, or
- `DISMISSED`.

Unreviewed prior model output is omitted.

## Bounded prior model text

At most 12 reviewed recommendations are included. For each one, only a small historical proposal identity is supplied:

- title
- area
- suggested priority

The previous model's `why`, `next_step`, diagnosis, creative variants, campaign brief and full output are not reinjected. The historical proposal is marked explicitly as prior AI output, not verified fact.

## Human handoff outcomes

When present, `APPLIED` or `NOT_APPLIED` is included as operator continuity evidence.

`APPLIED` means only that a human closed the handoff as applied. It does not prove that a provider, CRM, publishing, campaign, creative or paid-media mutation actually occurred.

## Observational follow-up

The current state from the post-application evidence layer may be included, such as `OBSERVATION_WINDOW`, `CAPTURE_DUE`, `EVIDENCE_AVAILABLE` or `POST_SNAPSHOT_NO_TARGET_SIGNAL`.

This is **no causal attribution**. A later snapshot or metric does not prove that Astra or the historical recommendation caused a result, and it is never converted into an automatic success/failure score.

## Provider interpretation rules

The context and system prompt instruct Astra to:

- treat historical proposal text as untrusted prior model output;
- treat human review and handoff outcomes as continuity signals, not performance scores;
- not interpret `APPLIED` as execution proof;
- not interpret later evidence as causal proof;
- avoid mechanically repeating `DISMISSED` or `NOT_APPLIED` proposals unless current supplied context materially justifies revisiting them;
- not automatically prefer or prioritize `ACCEPTED` or `APPLIED` proposals merely because they were accepted before.

## Privacy and authority

The feedback context contains no contact PII, provider secrets or media bytes. It adds no tool execution, provider mutation, CRM mutation, publishing, paid-media activation, scheduling or autonomous action authority.

Existing explicit generation remains the only provider-call path. Results freshness guards remain authoritative for campaign AI.

## Persistence

No new durable store is introduced. The projection is reconstructed from already durable local artifacts:

- AI sessions
- recommendation reviews
- handoff resolutions
- post-application evidence projection

The generated AI session continues to persist its sanitized context and context SHA-256 under the existing Wave 51 contract.

## macOS development bundle

The isolated post-W99 development bundle must include:

- `ai_human_feedback_context.py`
- `service_post_w99_ai_human_feedback_context_app.py`

The bundle remains:

- `release_authority: false`
- `physical_uat_authority: false`
- `w100: false`

## Frozen release boundary

Canonical W99 `main` remains frozen at:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

This increment is developed only on the post-W99 development line and does not certify physical UAT or create a release.

## Workflow guard

The repository remains limited to exactly:

1. `ci.yml`
2. `full-mac-app.yml`
3. `persistent-release.yml`

No fourth workflow is introduced.
