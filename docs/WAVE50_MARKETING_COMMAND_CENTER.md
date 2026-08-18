# Wave 50 · Marketing Command Center

Wave 50 turns Inicio into a company-scoped control surface instead of a shallow summary page.

## Objective

A marketing operator should be able to open one screen and answer:
- what needs attention now;
- whether the company is operationally configured;
- how many campaigns and creatives are moving;
- what is scheduled or published;
- what paid-media plans exist;
- what CRM work is open;
- where to go next to resolve a gap.

The Command Center composes existing certified stores and APIs. It does not duplicate campaign, creative, social, paid-media or CRM engines.

## Local-only refresh

`GET /api/companies/{company_id}/command-center` is intentionally local-only.

It reads:
- company configuration;
- canonical Video Studio workspace;
- CampaignStore;
- CreativeStore / CompanyMedia;
- local SocialStore state;
- local PaidMediaStore state;
- CRMStore state;
- existing local operations dashboard.

It does **not** call remote Meta analytics, paid-media observability, Inbox refresh or provider mutations.

The response exposes explicit safety evidence:
- `remote_refresh_performed: false`
- `provider_mutation_performed: false`

Remote readback stays user-triggered inside the Analytics, Inbox and Paid Media modules that already own those contracts.

## Operational readiness

The dashboard reports completion of eight local product prerequisites:
1. company Video Studio workspace;
2. Meta credential connection;
3. Facebook Page association;
4. Instagram professional account association;
5. Meta Ad Account association;
6. at least one campaign;
7. at least one profiled Creative Studio asset;
8. CRM with contacts.

Readiness is a product setup indicator, not a performance or marketing-quality score.

## Marketing flow

The top flow surfaces:
- active campaigns;
- creatives in production;
- creatives ready;
- scheduled publications;
- paid-media plans;
- open CRM opportunities.

Each number deep-links to the certified owning module.

## Priorities

Priorities are deterministic and generated from local state. Order:
1. failed publications;
2. overdue publications;
3. overdue CRM follow-ups;
4. unprofiled creative assets;
5. ready creatives without campaign;
6. campaigns without media;
7. local paid-media drafts requiring review;
8. missing setup/readiness components.

Wave 50 also preserves the Wave 43–45 `dailyFocus()` surface underneath the system priorities, including its explicit CRM complete/reschedule and editorial management behavior.

## Campaign cockpit

Active campaign cards summarize:
- status;
- objective;
- channels;
- audience size;
- linked creatives/media;
- linked publications.

Opening a card goes to the existing Campaign Center rather than creating a parallel campaign editor.

## Safety boundaries

Wave 50 adds no:
- direct remote publish-now action;
- automatic message/reply behavior;
- ad activation;
- automatic spend;
- automatic Meta polling;
- automatic provider analytics refresh.

All operational buttons deep-link to existing modules where their explicit confirmations and provider gates remain authoritative.

## macOS iteration

`build_full_mac_current.sh` remains arm64-only and now layers Wave 47 → Wave 48 → Wave 49 → Wave 50, then executes all four product audits before accepting the iteration bundle.
