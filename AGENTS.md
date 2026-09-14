# Antigravity / Agent Instructions — MKTGAPP

## Canonical identity
- Repository: `arendon7/MKTGAPP`
- Canonical integration branch: `main`
- Frozen release candidate SHA: `60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`
- This working branch: `antigravity/productization-v1`
- Product version intent: `0.9.0`
- Source release state: `PREPARED_RELEASE`
- Prepared tag intent: `v0.9.0`
- Runtime baseline: Wave 76

Do not write directly to `main` while the W99 physical-UAT candidate remains frozen. Do not create or move `v0.9.0` unless the release/UAT gates are explicitly completed.

## Mission
Continue and productize the existing BINARIO Marketing App. Do not restart the application, introduce a parallel product, or replace working modules just to change technology.

Immediate objective: make the existing product reliably runnable and usable for a real 30-day trial by one operator managing multiple companies.

## First actions after clone
1. Confirm current branch and SHA.
2. Use Python 3.12+.
3. Run `python -m unittest discover -s tests -v`.
4. Run `PYTHONPATH=src python -m binario_marketing.cli apps` (PowerShell: set `$env:PYTHONPATH='src'`).
5. Inventory launch/runtime paths, web UI, stores, provider adapters and persistence before changing architecture.
6. Produce a baseline audit of what actually runs locally.
7. Fix bootstrap/usability issues incrementally and keep tests green.

## Repository surfaces
- `src/` canonical Python application/core
- `web/` browser UI
- `api/` API/serverless entrypoints
- `apps/` manifest-driven app registry
- `native/` native/macOS integration
- `gateway/` integration/gateway surface
- `scripts/` build/audit/UAT/release tooling
- `tests/` regressions and behavior tests
- `docs/` wave-by-wave product contracts
- `.github/workflows/` CI/release workflows

## Existing product capabilities to preserve
- multi-company configuration/scoping
- Marketing Command Center
- Campaign Center
- Creative Studio
- social distribution/scheduler
- Paid Media Center
- CRM, Contact 360, opportunities, follow-ups and pipeline
- Inbox / Leads / Commercial Desk
- first-party capture and attribution
- Analytics & Learning Loop
- AI Copilot
- Video Editor
- App Factory / app registry
- UAT/release evidence machinery

Before adding a new domain module, find the current owning service/store/API and extend it instead of creating a parallel implementation.

## AI architecture
The current Copilot supports provider-neutral adapters for OpenAI, Anthropic, Gemini and Ollama. Preserve this layer.

Agents should be implemented above existing domain services through an orchestrator. Initial permissions:
- `READ_LOCAL`
- `READ_PROVIDER`
- `DRAFT_LOCAL`
- `MUTATE_LOCAL`
- `MUTATE_PROVIDER`
- `SPEND` (disabled by default)

Start specialized agents in proposal/draft mode. No silent publishing, messaging, CRM mutation, ad activation or spend.

Recommended first agents:
- Marketing Strategist
- Content Agent
- Inbox/Community Assistant
- CRM Follow-up Assistant
- Campaign Analyst
- Research Agent
- Video/Creative Assistant

## Security and data
- Never commit credentials.
- Prefer environment variables / OS keychain / deployment secret manager.
- Do not put provider tokens into project/company/session JSON.
- Preserve company isolation.
- Record non-secret provider/model/task/tool provenance for AI operations.
- Fail closed when identity, permission, credential or provider capability is ambiguous.

## Remote-action policy
Remote reads must be explicit/authorized. Mutating provider actions require explicit product permission and visible confirmation until a separate trusted automation policy is approved.

No autonomous ad spend.
No automatic message sending.
No automatic remote publish.
No inferred CRM-to-campaign attribution presented as causation.

## Productization priority
1. local bootstrap and reliable launch
2. favicon/app identity/broken assets/navigation/text polish
3. persistence/restart/data isolation
4. Inbox + CRM + lead workflows
5. Campaign + Creative + Social workflow
6. real provider health/connection flows
7. AI/agent orchestration
8. analytics/learning loop
9. 30-day trial instrumentation and error recovery
10. release/UAT completion

## Definition of usable V1
A non-developer operator can launch the app, choose a company, process leads/messages, work CRM, prepare campaigns/creatives, use AI safely, schedule/publish through authorized flows, review results, keep data across restarts and recover from ordinary errors without engineering intervention.

## External project context
Google Drive folder `MKTGAPP_ANTIGRAVITY_HANDOFF` is the companion knowledge/assets handoff. Treat Drive as context/assets only; Git remains the canonical source of code and history.
