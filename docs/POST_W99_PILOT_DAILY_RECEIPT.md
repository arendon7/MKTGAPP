# Post-W99 Pilot Daily Receipt

## Purpose

This increment turns the local pilot into a multi-day observable process. The operator can explicitly close a pilot work session and keep a small local receipt showing whether the Pilot Launch Gate was ready, which of its five checks passed, and how much of the pilot journey was observed.

The feature is **not production readiness**, is not analytics, is not an audit log of provider execution, and grants no release or business execution authority.

Frozen `main` remains exactly:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Development integration remains on `dev/post-w99-action-center` only.

## Data model

Receipts are stored locally at application-data scope under the pilot state area. The repository contains no user receipts.

Each immutable append-only receipt contains only:
- generated receipt id;
- browser-local calendar date (`YYYY-MM-DD`);
- UTC recorded timestamp;
- Gate ready/not-ready state;
- passed/total count for the five canonical launch checks;
- the five canonical check ids and booleans;
- pilot journey mode plus pass/total/ready state.

The ledger intentionally accepts **no free-form notes**. It does not store:
- company names or company ids;
- contacts or contact PII;
- campaign/content/message identifiers;
- provider ids or targeting;
- access tokens, credentials, secrets, prompts or AI output;
- filesystem paths, hashes or file contents.

The HTTP projection carries the same minimized structure plus aggregate counts of receipts and observed days.

## Day-based summary

Multiple explicit receipts may exist for the same local date. This preserves append-only evidence rather than silently editing history.

For the monthly summary:
- `receipt_count` counts all immutable receipts;
- `days_observed` counts unique local dates;
- `ready_days` evaluates the latest receipt for each date;
- `attention_days` is the remaining observed dates.

A later receipt on the same date therefore supersedes the earlier receipt **for the day summary only**; the earlier receipt remains present.

## Operator flow

#192 remains the launch/readiness authority. #193 adds two controls inside `Preparación piloto`:
- `Cerrar jornada` — explicit local POST that records the current minimized Gate evidence;
- `Historial del piloto` — local GET that shows the recent receipts and day summary.

Opening the Gate, viewing history, or normal navigation never creates a receipt. There is no timer, unload hook, polling loop, MutationObserver, automatic session close, or background write.

## Snapshot relationship

The receipt ledger lives inside the normal application data root, so a later Pilot Data Safety snapshot can include it.

`Cerrar jornada` does **not** create a snapshot automatically. After a receipt is written, an operator who wants the receipt included in recovery evidence must explicitly create a new snapshot from `Respaldo local`, then explicitly run `Probar recuperación` for that new snapshot.

This keeps snapshot creation and recovery rehearsal under their existing explicit owner controls instead of hiding those mutations inside the daily journal.

## Integrity and failure behavior

Writes use the repository's atomic JSON writer. Before every list or append operation, the entire persisted ledger is schema-validated.

If the local ledger is malformed or unsafe, the store fails closed:
- history returns an integrity failure;
- a new receipt is not appended;
- the corrupt file is not overwritten automatically.

Invalid request payloads are rejected independently as operator/input errors.

## Release and provider boundaries

The daily receipt feature adds no:
- Meta, Facebook, Instagram, ads or other provider reads;
- provider mutations or publication calls;
- AI provider calls;
- restore/delete authority;
- release, tag or deployment authority;
- production-ready claim.

The repository continues to use exactly these three canonical workflows:
- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

A month of healthy local receipts is pilot evidence only. Physical Apple Silicon UAT and the frozen W99 release route remain separate.
