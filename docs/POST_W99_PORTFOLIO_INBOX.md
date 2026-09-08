# Post-W99 · Portfolio Inbox

## Purpose

Make the primary **INBOX** destination useful for one operator managing many companies without introducing automatic Meta reads or a second social-inbox authority.

The flow is:

`explicit #174 refresh -> minimized local Inbox snapshots -> Portfolio Inbox -> exact owner handoff -> company Inbox`

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
- does not create a new store;
- reuses the current `inbox_attention()` projection, including reply/CRM suppression and blocking reconciliation states;
- preserves the existing attention `rank` as priority authority;
- caps the displayed global queue at 100 items;
- exposes only minimized fields already allowed by the local attention snapshot.

No Facebook/Instagram mapping IDs, Meta person IDs, provider links, raw provider errors or full provider response bodies are added to this projection.

## Explicit refresh reuse

The aggregate Inbox button **Actualizar todas desde Meta** calls the exact explicit #174 browser authority `postW99PortfolioInboxRefreshRun`.

There is still only one multi-company provider-read operation:

`POST /api/portfolio/inbox-refresh`

It keeps the #174 confirmation, 50-company bound, sequential provider reads, per-company failure isolation and no automatic retry. #175 does not add another POST path.

After an explicit batch refresh, Portfolio Inbox reloads the local projection. Merely opening or filtering the aggregate Inbox performs no provider read.

## Safety

- no polling;
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
