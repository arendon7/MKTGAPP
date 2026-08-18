# Wave 52 · Analytics & Learning Loop

Wave 52 turns the existing organic, paid-media and CRM surfaces into a durable evidence loop without pretending that correlation is attribution.

## Canonical loop

1. Campaign + Creative Studio define intent and relationships.
2. Organic publication and Paid Media create provider-facing objects through existing certified flows.
3. The user explicitly presses **Actualizar resultados desde Meta**.
4. Binario performs read-only provider calls through existing observability clients.
5. A sanitized local snapshot is persisted.
6. The snapshot is rolled up through existing links:
   - creative → organic publication;
   - creative → paid-media draft;
   - campaign → creative.
7. CRM company outcomes are captured as aggregate counts/value by currency.
8. The user records a local decision: `SCALE`, `ITERATE`, `HOLD` or `RETIRE`.
9. AI Copilot receives the latest sanitized evidence and the attribution caveat on the next explicit generation.

No decision is executed automatically.

## Evidence model

Schema: `binario.marketing.learning-snapshot.v1`

Each snapshot persists only sanitized analytical evidence:

- organic metrics supported by the certified Meta readback;
- Paid Media metrics supported by the certified Ads observability path;
- explicit coverage counts and provider-read errors as non-secret flags/types;
- aggregate CRM opportunity outcomes/value by currency;
- capture date preset and timestamp.

Provider credentials, contact records and media bytes are not part of the snapshot.

### Organic metrics

The current supported set is:

- reach;
- views;
- likes;
- comments;
- shares;
- saved;
- total interactions.

Wave 52 never fabricates a Facebook metric that the underlying certified readback does not expose.

### Paid metrics

The persisted additive totals are:

- impressions;
- reach;
- clicks;
- spend.

Derived metrics are calculated from totals when possible:

- CTR = clicks / impressions;
- CPC = spend / clicks;
- CPM = spend × 1000 / impressions;
- frequency = impressions / reach.

Binario does not convert currencies. If multiple currencies were ever present in one evidence set, spend must not be interpreted as one normalized monetary amount.

## Attribution boundary

Wave 52 explicitly reports:

- creative → publication: linked;
- creative → paid-media plan: linked;
- campaign → creative: linked;
- CRM → campaign: **not attributed**.

Current CRM opportunities do not yet contain a certified campaign/source/UTM attribution key. Therefore won opportunities and values are displayed only as company-level outcome signals.

This is intentional. Wave 52 must not label a CRM sale as caused by a campaign merely because both exist in the same period.

## Decisions

Schema: `binario.marketing.learning-decision.v1`

A decision contains:

- entity kind: campaign or creative;
- entity ID;
- action: `SCALE`, `ITERATE`, `HOLD`, `RETIRE`;
- rationale;
- optional evidence snapshot ID;
- timestamp.

A decision is durable local memory. It does not:

- activate or pause Ads;
- alter budgets;
- publish or cancel social content;
- modify campaign status;
- send CRM messages.

## AI Copilot

Wave 52 extends the Wave 51 sanitized AI context with:

- latest evidence snapshot metadata;
- campaign performance rollups;
- creative performance rollups;
- relative observed leaders;
- latest local decision action;
- company-level CRM outcome aggregates;
- explicit `crm_to_campaign: false` attribution state.

AI generation remains explicit and provider-neutral. The Copilot still has no provider tools or authority to mutate remote marketing systems.

## HTTP surface

Read-only local state:

- `GET /api/companies/{company_id}/learning`

Explicit provider readback + local snapshot:

- `POST /api/companies/{company_id}/learning/refresh`

Explicit local decision:

- `POST /api/companies/{company_id}/learning/decisions`

`GET /learning-loop.js` serves the Wave 52 browser bundle.

## Safety invariants

Wave 52 adds no:

- background polling;
- Ads activation route;
- automatic spend;
- automatic publication;
- automatic decision execution;
- CRM attribution guess;
- provider credential persistence in analytical state.

The remote refresh is always user-triggered and read-only.

## macOS iteration

`build_full_mac_current.sh` remains arm64-only and layers Wave 52 after Waves 47–51. The app must pass all historical audits plus `audit_wave52_learning_loop.sh` and the existing deep FULL MAC smoke before it is accepted as an iteration candidate.
