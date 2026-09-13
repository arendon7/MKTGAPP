# Post-W99 Pilot Session Status

## Boundary

This increment belongs only to the post-W99 development chain. Canonical `main` remains frozen at:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

The feature is for local pilot operation and is **not production readiness** and not release authority.

## Purpose

A month-long pilot needs a simple answer to a narrower question than company readiness: is the current local MERCADEO APP session healthy enough to continue working?

`Estado piloto` therefore reports only:

- local backend response;
- read access to four already-authoritative durable stores: companies, projects, campaigns and publications;
- passive pilot journey evidence already owned by `pilotJourneyReport()`;
- existence and basic metadata of the latest local snapshot already owned by Pilot Data Safety.

It does not create a new product readiness engine.

## W50 remains authoritative

Company onboarding/readiness remains owned by Command Center/W50. This increment does not copy the W50 step order, does not evaluate Meta readiness and does not infer that a company is ready for publishing or paid media.

The UI explicitly distinguishes local session `READY` from company/provider readiness.

## Endpoint

`GET /api/pilot-session/status`

The projection is minimized. It contains statuses and counts only. It does not expose:

- `data_root` or absolute/local paths;
- per-file paths;
- SHA-256 hashes;
- provider identifiers beyond counts already represented by local stores;
- Meta/AI credentials or credential source;
- access tokens, client secrets or authorization material.

The endpoint performs no provider read and no provider mutation.

## Store probes

The endpoint calls existing read APIs only:

- `companies.list()`;
- `projects.list_projects()`;
- `campaigns.list()`;
- `social.list()`.

A failed store read degrades the pilot session projection without mutating or repairing that store. Exception messages are not projected to the browser.

## Snapshot behavior

The endpoint reuses `PilotDataSafety.list_snapshots()` and shows only the latest public snapshot metadata plus count.

It intentionally does **not** call `verify_snapshot()` automatically because integrity verification can hash large local media collections. Verification remains an explicit operator action inside `Respaldo local`.

Therefore `integrity_checked` is false in the session projection. `Estado piloto` never implies snapshot integrity unless the operator explicitly verifies it in the existing safety panel.

## Browser behavior

`web/pilot-session-status.js` adds one `Estado piloto` action.

It fetches the local status only when the operator opens the panel or presses `Actualizar`. There is:

- no background polling;
- no `MutationObserver`;
- no automatic navigation;
- no form submission;
- no provider API call;
- no provider mutation;
- no publishing;
- no campaign activation;
- no CRM mutation;
- no AI execution.

The panel delegates existing workflows instead of duplicating them:

- `Abrir recorrido` -> `pilotJourneyShow()`;
- `Abrir respaldo` -> `pilotDataSafetyOpen()`.

The journey score comes from `pilotJourneyReport()` and therefore remains passive session evidence, not remote execution proof.

## Runtime chain

The cumulative dev terminal becomes:

`service_post_w99_pilot_session_status_app`

which extends:

`service_post_w99_pilot_data_safety_app`

The canonical release `serve` path is unchanged. The three canonical workflows remain exactly:

- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

No release tag, GitHub Release, production claim or physical UAT authority is introduced by this increment.
