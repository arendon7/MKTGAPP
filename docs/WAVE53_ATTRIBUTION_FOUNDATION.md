# Wave 53 · Attribution Foundation

Wave 53 adds the first deterministic bridge from marketing instrumentation to CRM outcomes.

The core rule is deliberately conservative:

> **A tracked URL is instrumentation, not evidence of a click or conversion.**

Binario attributes a CRM record only when the exact first-party tracking code (`bm_tid`) generated for a campaign/creative is captured by a landing page, form or integration and then explicitly bound to a CRM contact or opportunity.

## Canonical funnel

1. A campaign exists in Campaign Center.
2. Optionally, a Creative Studio item is linked to that campaign.
3. The user creates a tracking URL from an HTTPS destination.
4. Binario preserves the destination and appends standard manual campaign parameters plus `bm_tid`.
5. The URL may be used in organic content, Ads, email, WhatsApp or another channel.
6. An external landing/form/integration may capture the exact `bm_tid` submitted by the visitor.
7. The user or future certified integration records that captured code against a CRM contact/opportunity.
8. Binario resolves the original tracking link and therefore its campaign/creative.
9. CRM outcome/value can then be reported as **deterministically attributed for that captured record**.

No campaign is selected manually when a claim is recorded; campaign/creative identity comes from the immutable tracking-link record.

## URL instrumentation

Schema: `binario.marketing.tracking-link.v1`

A tracking link contains:

- durable company ID;
- durable campaign ID;
- optional Creative Studio media ID;
- original HTTPS destination;
- generated tracked URL;
- first-party `bm_tid`;
- `utm_source`;
- `utm_medium`;
- `utm_campaign`;
- `utm_id`;
- optional `utm_content`;
- optional `utm_term`;
- optional `utm_source_platform`;
- creation timestamp.

Binario preserves unrelated destination query parameters but replaces any previously supplied managed UTM fields and `bm_tid` so one generated link has one canonical instrumentation identity.

The destination must:

- use HTTPS;
- be absolute and have a host;
- contain no embedded username/password;
- contain no credential-like query parameters such as access tokens or passwords.

Creating this record performs no network request and does not create a click event.

## Captured attribution evidence

Schema: `binario.marketing.attribution-claim.v1`

The only Wave 53 attribution evidence type is:

`CAPTURED_TRACKING_CODE`

A claim contains:

- exact captured `bm_tid`/tracking code;
- resolved tracking-link ID;
- optional CRM contact ID;
- optional CRM opportunity ID;
- captured timestamp;
- durable creation timestamp.

A claim requires at least a contact or opportunity. Company boundaries are enforced for tracking links, contacts and opportunities.

Wave 53 explicitly rejects date correlation or a remembered/manual campaign selection as attribution evidence.

## Multi-touch and credit

All deterministic captured touchpoints are retained.

However, a CRM opportunity may capture more than one valid `bm_tid` during its lifecycle. To prevent double counting, Wave 53 uses:

`LAST_CAPTURED_TOUCH`

For opportunity/value rollups:

- every captured claim remains visible as a touch;
- each opportunity is credited at most once;
- its CRM value is credited at most once;
- the credit goes to the latest captured deterministic touch;
- campaign and creative rollups therefore cannot duplicate the same opportunity value merely because multiple touches exist.

This is an accounting rule for deterministic captured evidence, not a claim that last-touch is the only causal marketing model.

## Coverage, not universal attribution

Wave 52 correctly reported CRM → campaign as un-attributed because no certified source key existed.

Wave 53 does **not** replace that with a universal attribution claim. Instead it introduces partial deterministic coverage:

- records with a captured `bm_tid`: attributable under the Wave 53 model;
- records without a captured `bm_tid`: remain unattributed;
- coverage percentage is reported explicitly.

The Learning Loop exposes:

- `crm_to_campaign_deterministic_partial`;
- `crm_to_campaign_coverage_percent`;
- `crm_attribution_model = LAST_CAPTURED_TOUCH`.

No temporal inference is performed for the remaining CRM records.

## Currency safety

CRM opportunity values remain grouped by their native three-letter currency.

Wave 53 never adds values from different currencies into a normalized total and performs no FX conversion.

## AI Copilot boundary

The AI context receives only aggregate attribution evidence:

- attribution model;
- coverage;
- attributed counts;
- attributed values by currency;
- campaign-level aggregates;
- creative-level aggregates.

The AI context does not include:

- contact names;
- emails;
- phone/WhatsApp numbers;
- contact IDs;
- individual `bm_tid` values;
- tracked URLs;
- provider credentials.

AI remains advisory only and cannot create claims, mutate CRM, publish, activate Ads or spend budget.

## HTTP surface

Local read-only state:

- `GET /api/companies/{company_id}/attribution`

Explicit local instrumentation:

- `POST /api/companies/{company_id}/attribution/links`

Explicit local captured evidence:

- `POST /api/companies/{company_id}/attribution/claims`

Browser bundle:

- `GET /attribution-foundation.js`

No route records redirects or public clicks in Wave 53.

## Safety invariants

Wave 53 adds no:

- background polling;
- public redirect/click collector;
- temporal attribution guess;
- automatic CRM mutation;
- automatic campaign selection for a captured code;
- provider API call;
- provider mutation;
- Ads activation;
- automatic spend;
- automatic publication;
- cross-currency value aggregation.

## Next layer

The natural later extension is a separately deployed, privacy-reviewed first-party capture/landing integration that can safely persist `bm_tid` into lead submissions or CRM ingestion. Such a collector is **not** part of Wave 53 and must not be simulated by the localhost desktop application.

## macOS iteration

`build_full_mac_current.sh` remains arm64-only and layers `service_wave53_app` after Wave 52. Acceptance requires all historical audits, the Wave 53 attribution audit, Source CI and the deep FULL MAC arm64 smoke.
