# Post-W99 Pilot Month Tracker

## Purpose

This increment turns the append-only pilot daily receipts from #193 into a simple operator-facing 30-day view.

The tracker is presentation only. It helps answer three practical questions during the test month:
- on how many of the last 30 calendar days was a pilot receipt explicitly recorded;
- how many of those latest daily receipts were `LISTO` versus `ATENCIÓN`;
- how many consecutive calendar days, ending today, have an explicit receipt.

It is **not production readiness**, provider observability, employee monitoring, an analytics score, or release authority.

Frozen `main` remains exactly:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Development integration remains on `dev/post-w99-action-center` only.

## Existing authority reused

#194 adds no business API and no persistence model.

The browser reads the existing local endpoint from #193:

`GET /api/pilot/daily-receipts?limit=365`

The server still owns the canonical append-only ledger and its minimized projection. The month tracker does not parse files directly and does not create a second receipt store.

## 30-day model

The view covers today plus the previous 29 browser-local calendar dates.

For each date, only the latest receipt already returned by the canonical ledger is used for presentation:
- `LISTO` when that receipt's Pilot Launch Gate was ready;
- `ATENCIÓN` when a receipt exists but the gate was not ready;
- `SIN REGISTRO` when no explicit receipt exists for that date.

The view also derives:
- days observed;
- days ready;
- days with attention;
- days without a receipt;
- current receipt streak ending today.

These values are descriptive only. A missing receipt does not mean the application failed or that no work occurred.

## Operator flow

`Preparación piloto` gains one additional action:

`Seguimiento 30 días`

The action is explicit. Opening it performs one local GET and renders the calendar. Normal navigation does not load receipt history in the background.

There is no polling, interval, MutationObserver, unload hook, localStorage, sessionStorage or automatic write.

## Safety and privacy

The tracker adds no:
- POST, PATCH, PUT or DELETE route;
- receipt mutation;
- snapshot creation, restore or deletion;
- Meta/Facebook/Instagram/provider read or mutation;
- AI provider call;
- company/contact PII projection;
- filesystem path or hash projection;
- publication, scheduling or paid-media authority;
- tag, deployment, release or production-ready authority.

## Runtime composition

`service_post_w99_pilot_month_tracker_app` extends the #193 daily-receipt terminal only to serve `pilot-month-tracker.js` and append its loader after `pilot-daily-receipt.js`.

`service_post_w99_dev_app` advances to this terminal. Canonical `serve` remains frozen and separate.

The repository continues to contain exactly three canonical workflows:
- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

The physical Apple Silicon UAT and W99 release route remain unchanged.
