# Post-W99 · Portfolio Inbox

## Purpose

Make the primary **INBOX** destination useful for one operator managing many companies without introducing automatic Meta reads or a second social-inbox authority.

Canonical flow:

`explicit selective refresh -> minimized local Inbox snapshots -> Portfolio Inbox -> exact owner handoff -> company Inbox`

## Default experience

Opening **INBOX** from primary navigation shows **Todas las empresas** first. The projection aggregates only active companies with Facebook or Instagram Inbox mappings and only the minimized evidence already retained by `InboxAttentionStore`.

The operator can filter:

- all pending interactions;
- Facebook messages;
- Instagram comments;
- reply-verification blockers.

Each item carries its exact company, interaction kind and interaction ID. **Abrir en empresa** switches to that company and hands the exact target to the existing Inbox owner. The company Inbox remains responsible for provider refresh, replies, reply reconciliation and CRM actions.

A direct Action Center / Today handoff to an Inbox interaction still opens the owning company instead of the aggregate view.

## Local projection contract

`GET /api/portfolio/inbox-attention`

is local and read-only. It:

- does not call Meta;
- does not mutate CRM;
- does not reply;
- does not publish;
- does not invoke AI;
- does not create a new durable message store;
- reuses the current `inbox_attention()` projection, including reply/CRM suppression and blocking reconciliation states;
- preserves the existing attention `rank` as priority authority;
- caps the displayed global queue at 100 items while exposing the full observed count;
- re-minimizes every cross-company item through an explicit field allowlist before exposing it.

The cross-company boundary accepts only the fields needed to identify and explain the pending local action: interaction kind/ID, observed time, actor handle, exact local CRM contact ID when already resolved, excerpt, reply eligibility, attention kind, rank/urgency/blocking state, title/detail and reason code. Excerpts remain capped at 280 characters, and other display/identifier fields are normalized and bounded before projection.

Unexpected future snapshot fields are discarded by default. Facebook/Instagram mapping IDs, Meta person IDs, provider links, raw provider errors, sender/recipient graphs and full provider response bodies cannot cross the Portfolio Inbox merely because a lower-level snapshot later evolves.

## Explicit selective refresh reuse

The aggregate Inbox button **Actualizar Inbox pendiente** calls the exact browser authority `postW99PortfolioInboxRefreshRun` already used by Today.

The refresh plan remains local-only and exposes `refresh_company_ids`. Only companies whose local Inbox-attention snapshot requires refresh are sent to the existing batch POST. CURRENT snapshots are skipped by default.

There is still only one multi-company provider-read operation:

`POST /api/portfolio/inbox-refresh`

It keeps the explicit confirmation, active/mapped revalidation, maximum 50 requested companies, sequential provider reads, per-company failure isolation and no automatic retry. Portfolio Inbox adds no second POST path.

After an explicit refresh, Portfolio Inbox reloads the local projection. Merely opening or filtering the aggregate Inbox performs no provider read.

## Safety

- sin polling;
- no background Meta Inbox reads;
- no automatic replies;
- no automatic CRM creation;
- no automatic publishing;
- no automatic AI generation;
- no fuzzy cross-company identity matching;
- no second priority engine;
- no new GitHub Actions workflow.

The repository remains at exactly:

- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

## Release boundary

This is isolated post-W99 development only. It has no release authority, no physical-UAT authority and is not W100.

Canonical frozen W99 `main` remains:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

with canonical tree:

`53d1cf04a67da4308b37ac03c0be4546a04f36eb`
