# MERCADEO APP / BINARIO Marketing IA — engineering guardrails

This repository is the canonical source for `arendon7/MKTGAPP`.

## Current branch contract

- `main` is frozen at W99: `60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`.
- Do not push or merge source changes to `main` while the exact W99 physical Apple Silicon UAT remains open.
- Post-W99 product development integrates through `dev/post-w99-action-center`.
- New feature branches should start from the current head of `dev/post-w99-action-center` and target that branch with a PR.
- A post-W99 merge does not create W100, release authority, publication authority, production readiness, a Git tag, or a GitHub Release.

## Product goal

Build a simple multi-company Marketing Operating System for one operator: companies/brands, CRM, Inbox, content, calendar/scheduling, campaigns, paid media, Creative/Video Studio, analytics/results, and human-governed AI assistance.

The product is local-first. Cloud execution exists only where explicitly implemented and bounded.

## Local development

Python requirement: 3.12+.

```bash
PYTHONPATH=src python3 -m binario_marketing.cli serve-dev --host 127.0.0.1 --port 8766 --open
```

Run the complete source suite before proposing integration:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Useful read-only diagnostics:

```bash
PYTHONPATH=src python3 -m binario_marketing.cli runtime
PYTHONPATH=src python3 -m binario_marketing.cli meta-status
```

The standard post-W99 development entrypoint is `binario_marketing.cli serve-dev`, which resolves to `service_post_w99_dev_app`. Do not bypass that alias when adding a new cumulative post-W99 terminal.

## Safety and authority boundaries

- No credentials, access tokens, provider person IDs, private message bodies, or other secrets in Git, fixtures, logs, cross-company projections, or browser persistence.
- Provider reads/writes must remain explicit and must reuse the existing authority for that operation; do not create duplicate execution paths.
- Do not add background polling, auto-replies, automatic CRM mutation, automatic campaign activation, or autonomous AI execution unless a future task explicitly changes the product authority model.
- AI recommendations are advisory. Human review/acceptance is not execution proof.
- Preserve fail-closed behavior for ambiguous external side effects.
- Keep company ownership explicit on every cross-company handoff.
- Cross-company surfaces should minimize fields and hand mutation authority back to the exact owning company/module.
- Keep the repository at exactly the three canonical GitHub workflows unless a separately reviewed infrastructure change explicitly authorizes otherwise.

## Development discipline

1. Reuse existing canonical owner projections instead of inventing a second scoring, scheduling, results, or mutation engine.
2. Add focused pure/runtime/HTTP/browser tests for new behavior.
3. Keep bundle build/audit/smoke cumulative when a feature changes the packaged post-W99 app.
4. Verify the exact feature head in Canonical Source CI and both Mac workflows before merge.
5. Merge only into `dev/post-w99-action-center` while W99 `main` is frozen.
6. Keep product copy concise and operator-oriented; current application UI is primarily Spanish.

## User data

User data lives outside the repository, by default under `~/Documents/Binario IA/`. Tests must use temporary data roots and must not depend on a developer's real workspace.
