# Post-W99 · Campaign Results Owner Handoff

## Problem

Action Center already carries a canonical `campaign_id` for campaign work, but several results-oriented actions still ended at the generic `analytics` owner:

- `capture_results`
- `review_coverage`
- `record_decision`
- `review_results`

`Contextual Deep Linking` did not define an analytics campaign target, so these actions became `OWNER_ONLY`. The user reached the right module but still had to recover the campaign context manually. In `intelligence`, `optional_ai` already reached the exact W65 campaign card, but Control Handoff highlighted the generic `Ir` button instead of the existing explicit `Analizar con IA` owner control.

This increment closes those gaps without creating a second learning, decision or AI authority.

## Local exact context projection

New GET-only endpoint:

`GET /api/companies/{company_id}/campaigns/{campaign_id}/results-owner-context`

Schema:

`binario.marketing.campaign-results-owner-context.v1`

The projection validates the exact campaign through `CampaignStore.get_for_company`, then composes only local state already owned by:

- Campaign Store;
- Wave 52 Learning Loop;
- Wave 65 Results Intelligence.

It returns compact campaign identity, latest local snapshot, campaign learning row when available, W65 evidence/attribution/decision/next-action context and capability metadata for the canonical owner controls.

The projection itself performs:

- no provider read;
- no provider mutation;
- no business mutation;
- no AI generation;
- no background polling.

This GET is necessary for `capture_results`: before the first W52 snapshot, `learning_payload` intentionally has `campaigns=[]`, so the browser cannot truthfully claim that a campaign row exists in Learning Loop. The exact local campaign read supplies identity without fabricating evidence.

## Browser target

Schema:

`binario.marketing.campaign-results-owner-handoff.v1`

For analytics actions with a canonical `campaign_id`, the adapter changes the deep-link target from `OWNER_ONLY` to:

- `target_kind = CAMPAIGN_RESULTS`
- `target_id = campaign_id`

Before declaring the owner ready it requires:

1. selected company exists;
2. the local results-owner-context GET returns for the same company and campaign;
3. W52 Learning Loop local payload is loaded;
4. the owner is in the `learning` tab.

Only then does it inject one read-only exact campaign context card carrying `data-deep-results-campaign-id`.

The card shows:

- campaign name/objective/status/channels;
- latest snapshot or `Sin snapshot`;
- evidence summary;
- attributed opportunity count;
- latest human decision.

It is navigation/context, not a replacement analytics engine.

## Owner controls

### `capture_results`

Handoff resolves the existing W52 button:

`Actualizar resultados desde Meta`

The adapter never presses it. Wave 52 retains its existing confirmation dialog. Only after explicit human confirmation may W52 read Meta and store a sanitized local snapshot.

### `review_coverage`

Handoff resolves the exact campaign context as a `READ_ONLY_SURFACE`. The surface exposes observed evidence and attribution coverage without provider reads or inferred causality.

### `record_decision`

The exact context adds one adapter button:

`Preparar decisión para esta campaña`

That button is deliberately not a business mutation. Only after the user clicks it does the adapter:

- keep the canonical W52 decision form;
- set its entity kind to `CAMPAIGN`;
- repopulate the campaign selector from the already-loaded W52 campaign rows;
- select the exact `campaign_id`;
- move focus to the rationale field.

No synthetic click or submit occurs. After preparation, Control Handoff moves to the canonical W52 form and the user must still choose `SCALE / ITERATE / HOLD / RETIRE`, write rationale and submit `Registrar decisión local`.

If the campaign is not present in the current W52 snapshot, preparation fails closed.

### `review_results`

Handoff resolves the exact read-only campaign results context. No control or recommendation is executed.

### `optional_ai`

For the already-exact W65 `CAMPAIGN_INTELLIGENCE` card, handoff now resolves the existing `Analizar con IA` button instead of the generic `Ir` button.

W65 keeps all authority:

- evidence must exist;
- AI provider/model must be configured;
- the button remains disabled while generation is running;
- the user receives the existing explicit confirmation before sanitized context is sent;
- AI recommendations obtain no marketing execution authority.

## Safety

The browser adapter contains no POST/PATCH/PUT/DELETE transport. Its only API call is the local GET results-owner-context projection.

It does not use:

- synthetic `.click()`;
- `dispatchEvent()`;
- `setInterval()`;
- `sendBeacon()`;
- automatic provider reads;
- automatic AI generation;
- automatic decision submit;
- fuzzy campaign matching;
- title-based identity matching.

The only form-value preparation occurs **after an explicit human click** on `Preparar decisión para esta campaña` and affects UI state only. Business state remains untouched until the canonical W52 submit.

## Composition

`service_post_w99_campaign_results_owner_handoff_app` inherits the certified Existing Activity Reschedule Control terminal and adds only the local GET projection + browser adapter.

Browser composition becomes:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff`

## Deliberate remaining gap

This increment does not solve the separate W64 second-hop execution relay. `FIX_EXECUTION` can still reach the exact W64 campaign and then require `Ir` to move to its next owner. That should be addressed separately because final W64 destinations have different identity contracts (campaign, media, publication, paid draft) and must not be guessed.

## Frozen release boundary

This work lives only in post-W99 development. It does not modify:

- `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`;
- tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`;
- W99 physical UAT candidate;
- issue #113 authority;
- tag intent `v0.9.0`;
- canonical `serve`;
- release/publish gates.

It is not W100, physical-UAT PASS, a release candidate, publication authority or production-ready status.
