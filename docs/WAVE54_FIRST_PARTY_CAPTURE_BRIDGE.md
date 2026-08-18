# Wave 54 · First-Party Capture Bridge

Wave 54 closes the operational gap left intentionally open by Wave 53: a tracked URL can now carry its deterministic `bm_tid` through a first-party landing/form and into BINARIO CRM without a user manually copying that code.

This wave does **not** add a click collector, redirect service, advertising pixel, third-party cookie, provider webhook, background poller, automatic submit or automatic Ads/publication mutation.

## 1. Evidence model

The evidence chain is:

`TrackingLink (W53) -> browser hidden fields -> CRM payload -> FirstPartyCapture -> AttributionClaim -> CRM outcome`

The browser never chooses campaign identity. `bm_tid` resolves to the immutable Wave 53 tracking link on the server. Captured UTM values are corroborating data only.

### Canonical checks

For a capture to be accepted:

1. the company must exist;
2. `bm_tid` must resolve to a tracking link belonging to that company;
3. any supplied UTM value must equal the canonical value on that tracking link;
4. CRM contact/opportunity references must belong to the same company;
5. an opportunity/contact pair must be internally consistent;
6. credential-like fields are rejected;
7. malformed URLs, ids, bridge versions or timestamps fail closed.

A captured UTM mismatch is rejected **before** a CRM create/update is executed.

## 2. Server receive time is authoritative

The portable browser script includes `bm_client_captured_at`, but that field is metadata only.

For deterministic ordering and Wave 53 `LAST_CAPTURED_TOUCH` credit, BINARIO uses the time the capture is received and persisted by the local server. A manipulated browser clock therefore cannot reorder attribution.

Wave 53 manual attribution claims remain available as an explicit expert operation; Wave 54 automatic bridge captures use server receive time.

## 3. Portable browser bridge

File:

`web/first-party-capture-bridge.js`

Properties:

- no external dependency;
- no `fetch`;
- no `XMLHttpRequest`;
- no `sendBeacon`;
- no form submit/requestSubmit;
- no `setInterval`;
- no cookie or `localStorage`;
- transient same-tab persistence through `sessionStorage` only;
- dynamic forms supported through `MutationObserver`;
- an invalid explicit `bm_tid` clears the current session attribution instead of falling back to stale attribution;
- URLs written into hidden fields exclude query strings and fragments.

The script should be hosted on the same first-party website as the landing/form. External websites must never depend on the desktop app's `localhost` origin.

Example installation after copying the portable file into the website:

```html
<script src="/assets/binario-first-party-capture-bridge.js" defer></script>
```

A form may opt out with:

```html
<form data-binario-attribution="off">
```

## 4. Hidden-field contract

When a valid `bm_tid` is present, the bridge can add:

- `bm_tid`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_id`
- `utm_content`
- `utm_term`
- `utm_source_platform`
- `bm_client_captured_at`
- `bm_landing_url`
- `bm_referrer_url`
- `bm_bridge_version`

`bm_landing_url` and `bm_referrer_url` are already stripped to origin + pathname in the browser. The server performs a second minimization and persists only host/port.

## 5. CRM integration

### Existing CRM create/update endpoints

Wave 54 extends the existing company-scoped contact and opportunity mutations with one optional nested key:

```json
{
  "name": "Lead",
  "email": "lead@example.com",
  "attribution_capture": {
    "bm_tid": "bm_...",
    "utm_source": "instagram",
    "utm_medium": "paid_social",
    "utm_campaign": "campaign_name",
    "utm_id": "campaign_...",
    "client_captured_at": "2026-08-18T06:00:00Z",
    "landing_url": "https://example.com/form",
    "referrer_url": "https://instagram.com/...",
    "bridge_version": "1.0.0"
  }
}
```

The bridge's `bm_*` metadata field names are intended for HTML forms. An integration maps:

- `bm_client_captured_at -> client_captured_at`
- `bm_landing_url -> landing_url`
- `bm_referrer_url -> referrer_url`
- `bm_bridge_version -> bridge_version`

The core `bm_tid` and standard UTM names remain unchanged.

Supported CRM mutation paths:

- contact create -> `CRM_CONTACT_CREATE`
- contact update -> `CRM_CONTACT_UPDATE`
- opportunity create -> `CRM_OPPORTUNITY_CREATE`
- opportunity update -> `CRM_OPPORTUNITY_UPDATE`

The normal CRM response shape remains unchanged for compatibility. Capture evidence is visible in the Capture Bridge / Attribution surfaces.

### Existing-record import endpoint

For a CRM record that already exists:

`POST /api/companies/{company_id}/attribution/captures`

Payload includes the capture fields plus at least one of:

- `contact_id`
- `opportunity_id`

Those imports are recorded with source `API_IMPORT`.

## 6. Durable capture store

File:

`src/binario_marketing/capture_store.py`

Schema:

`binario.marketing.first-party-capture.v1`

Persisted fields include:

- company id;
- tracking link id;
- tracking code;
- CRM ids;
- canonical UTM values;
- capture source;
- UTM validation state;
- landing hostname only;
- referrer hostname only;
- bridge version;
- client timestamp as non-authoritative metadata;
- authoritative server receive time.

The store deliberately does **not** persist:

- contact name;
- email;
- phone/WhatsApp;
- arbitrary form fields;
- full landing URL/query;
- full referrer URL/query;
- provider credentials;
- media bytes.

## 7. Idempotency

Capture storage is duplicate-safe for the same:

- tracking link;
- CRM contact/opportunity pair;
- capture source.

Wave 53 AttributionClaim remains duplicate-safe for the same tracking link + CRM reference set.

A contact and a later opportunity may therefore have separate evidence records while the opportunity itself is still credited only once by `LAST_CAPTURED_TOUCH`.

## 8. Product surface

Wave 54 adds first-class navigation:

**Capture Bridge · W54**

The workspace shows:

- capture totals;
- instrumented links;
- links with received captures;
- opportunity captures;
- portable script download;
- install snippet;
- form-to-CRM mapping contract;
- recent first-party captures;
- explicit evidence/safety semantics.

The portable script itself is exposed locally only for copying/downloading:

`GET /first-party-capture-bridge.js`

The management UI is:

`GET /capture-bridge.js`

## 9. APIs

Read-only local state:

`GET /api/companies/{company_id}/attribution/capture-bridge`

Explicit existing-record capture:

`POST /api/companies/{company_id}/attribution/captures`

The Wave 53 attribution endpoint keeps its schema and adds a `capture_bridge` summary so historical contracts do not drift.

## 10. Learning + AI privacy

Wave 52 learning state gains only aggregate capture counts.

AI context receives:

- capture record count;
- instrumented-link count;
- links-with-capture count;
- contact/opportunity capture counts;
- evidence semantics.

AI context does **not** receive:

- contact ids;
- names/emails/phones;
- `bm_tid` values;
- tracking URLs;
- landing/referrer hosts;
- full capture records.

## 11. Safety invariants

Wave 54 preserves all previous safety gates:

- creating a tracking URL is not click evidence;
- portable browser instrumentation performs no network call;
- portable browser instrumentation never submits a form;
- no provider activation;
- no Ads budget mutation;
- no automatic publishing;
- no provider polling;
- no date-correlation attribution;
- no cross-company capture;
- no cross-currency aggregation;
- no browser-controlled attribution ordering.

## 12. Current build scope

Wave 54 remains an **arm64 development iteration**.

It does not change:

- version `0.9.0.dev1`;
- development release channel;
- ad-hoc signing;
- notarization state (`false`);
- production readiness (`false`).

Acceptance requires Canonical Source CI on macOS + Ubuntu and FULL MAC arm64 with every historical audit plus `audit_wave54_capture_bridge.sh`.
