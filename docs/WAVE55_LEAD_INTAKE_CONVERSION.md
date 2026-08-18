# Wave 55 · Lead Intake & Conversion Connectors

Wave 55 separates inbound lead capture from CRM mutation. A form, CSV, local API integration or manual operation can create a durable lead candidate, but **intake never creates or updates a CRM contact/opportunity automatically**.

## Canonical flow

`external/form/CSV -> Lead Intake -> exact identity review -> explicit CRM conversion -> optional opportunity -> attribution evidence`

The purpose is to make lead ingestion safe enough to connect more sources later without turning every inbound row into uncontrolled CRM state.

## Lead schema

Durable schema:

`binario.marketing.lead-intake.v1`

A lead stores:

- company id;
- connector;
- optional external `source_ref`;
- contact candidate fields;
- canonical W53 tracking identity when a valid `bm_tid` was supplied;
- canonical UTM snapshot;
- authoritative server receive time;
- explicit conversion/dismissal state.

Supported connectors:

- `FIRST_PARTY_FORM`
- `CSV_IMPORT`
- `API_IMPORT`
- `MANUAL`

## Intake is not conversion

Creating a lead does not:

- create a contact;
- update a contact;
- create an opportunity;
- send WhatsApp/email/DM;
- publish content;
- activate or change Ads;
- call Meta or another provider.

CRM changes happen only under:

`POST /api/companies/{company_id}/lead-intake/{lead_id}/convert`

## Exact identity matching

Wave 55 deliberately avoids fuzzy identity inference.

Exact keys are:

- email: case-insensitive exact value;
- phone and WhatsApp: normalized digit identity, treated as the same phone namespace;
- Instagram: normalized exact handle, including `@handle` or Instagram profile URL forms.

A name is never used as a duplicate key.

Lead states:

- `NEW`: identity is present but no CRM match exists;
- `MATCHED`: exactly one CRM contact shares an exact identity;
- `CONFLICT`: more than one CRM contact shares an exact identity;
- `UNIDENTIFIED`: no exact identity field is available;
- `CONVERTED`: explicitly linked/created in CRM;
- `DISMISSED`: explicitly rejected.

## Duplicate intake candidates

Open leads sharing an exact identity are surfaced as duplicate candidates, but they are never merged automatically.

This keeps source records auditable and avoids destructive guesses when two submissions may represent separate events.

## Conversion rules

### CREATE_CONTACT

Allowed only when no exact CRM match exists. If a match exists, the operation fails closed and the user must link/resolve instead of creating a duplicate.

### LINK_CONTACT

If there is exactly one exact match it can be linked explicitly.

If there is a conflict, the user explicitly selects one of the exact candidates.

A nonexact manual link is supported only through API with `confirm_user_selected=true`; it is recorded as `USER_SELECTED_CONTACT` rather than pretending it was an identity match.

Conversion bases:

- `CREATED_NEW_CONTACT`
- `EXACT_IDENTITY_MATCH`
- `USER_SELECTED_CONTACT`

### Opportunity

Opportunity creation remains optional and explicit. It can be requested in the same conversion POST or later after the lead is linked to a contact.

## First-party attribution

When intake includes `attribution_capture`, Wave 55 delegates validation to the Wave 54 canonical validator:

1. `bm_tid` must resolve to a W53 tracking link belonging to the same company;
2. supplied UTM values must match the immutable tracking link;
3. mismatches fail before a lead is accepted;
4. intake stores the canonical tracking snapshot, not browser-selected campaign identity.

Because a FirstPartyCapture requires a CRM reference, Wave 55 does not materialize the W54 capture at intake time. It waits until explicit CRM conversion.

At conversion the canonical link is verified again and the evidence is materialized using the **original lead `received_at`**, not the later conversion time. This prevents an operator's review delay from changing `LAST_CAPTURED_TOUCH` ordering.

## Source reference idempotency

Within one company + connector, `source_ref` is an idempotency key.

- same `source_ref` + same normalized payload -> existing intake row is returned;
- same `source_ref` + different payload -> fail closed.

This protects connector retries from silently rewriting evidence.

## CSV intake

Endpoint:

`POST /api/companies/{company_id}/lead-intake/csv`

Limits:

- UTF-8;
- maximum 10 MiB;
- maximum 10,000 rows.

CSV accepts common English/Spanish contact aliases and optionally:

- `source_ref`
- `bm_tid`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_id`
- `utm_content`
- `utm_term`
- `utm_source_platform`

If attribution columns exist without `bm_tid`, the row is rejected.

When `source_ref` is absent, BINARIO generates:

`sha256:<file_sha256>:row:<row_number>`

Therefore exact reimport of the same file is idempotent.

CSV intake reports `crm_mutations: 0` and never uses the historical Wave 36 direct-contact CSV importer behind the scenes.

## Local API

Read company intake:

`GET /api/companies/{company_id}/lead-intake`

Read one lead:

`GET /api/companies/{company_id}/lead-intake/{lead_id}`

Create intake candidate:

`POST /api/companies/{company_id}/lead-intake`

Explicit conversion:

`POST /api/companies/{company_id}/lead-intake/{lead_id}/convert`

Explicit dismissal:

`POST /api/companies/{company_id}/lead-intake/{lead_id}/dismiss`

## Public ingress boundary

The desktop application remains loopback-local by default. Wave 55 does **not** claim to expose a public internet webhook.

A website or external SaaS should forward its submission server-side to a reachable integration/deployment layer. It must not depend on an end user's browser reaching the BINARIO desktop `localhost` origin.

A later wave may deploy a real authenticated collector/connector surface; Wave 55 establishes the durable local contract first.

## Product surface

The Marketing Ops shell gains:

**Lead Intake · W55**

It exposes:

- intake totals/open/matched/conflicts/converted/attributed;
- manual staging;
- CSV staging;
- exact-match visibility;
- open duplicate candidate warnings;
- explicit create/link/dismiss actions;
- explicit opportunity creation.

No polling is added.

## Learning and AI

Learning receives aggregate intake counts and coverage only.

AI context receives aggregate:

- total/open/converted/attributed counts;
- connector counts;
- identity coverage;
- conversion coverage;
- exact-match semantics.

AI does not receive:

- lead rows;
- lead ids;
- names;
- emails;
- phones;
- contact ids;
- `bm_tid` values;
- tracking URLs.

## Safety invariants

Wave 55 preserves all prior gates:

- no fuzzy identity guessing;
- no automatic CRM conversion;
- no automatic lead merge;
- no provider calls during intake;
- no automatic message send;
- no Ads activation/budget mutation;
- no automatic publishing;
- no background polling;
- no date-correlation attribution;
- no cross-company linking;
- no browser timestamp authority;
- no cross-currency aggregation.

## Current build scope

Wave 55 remains an arm64 development iteration:

- version `0.9.0.dev1`;
- development channel;
- ad-hoc signing;
- notarized: false;
- production-ready: false.

Acceptance requires Canonical Source CI on macOS + Ubuntu and FULL MAC arm64 with every historical audit plus `audit_wave55_lead_intake.sh`.
