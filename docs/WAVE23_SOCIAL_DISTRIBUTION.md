# Wave 23 — Social Distribution, Meta Publishing and Ads

## Goal

Extend BINARIO Marketing from content creation into controlled distribution without weakening the certified local editor/runtime.

## Non-negotiable contracts

1. Provider credentials never enter project JSON, artifact metadata, logs, browser state, or timeline payloads.
2. Social publication is durable and auditable: `DRAFT -> QUEUED -> PUBLISHING -> PUBLISHED|FAILED`.
3. Scheduled work must survive app restarts.
4. A local file is not represented as publishable Instagram media unless Meta can actually fetch it.
5. Paid media creation defaults to `PAUSED`; activation/spend is a separate explicit gate.
6. Provider adapters stay isolated from editor/render code.
7. Every external provider call must be testable through an injectable transport.

## 23A — Distribution core

Status: implemented on `feature/wave23-social-distribution`.

- durable publication store
- timezone-aware queue and due selection
- Meta Graph API client
- Facebook Page discovery and sanitized Page token handling
- Instagram professional-account discovery through linked Pages
- Facebook text/link/image publishing primitives
- Instagram image/Reel container + processing + publish primitives
- Meta ad account discovery
- campaign creation forced to `PAUSED`
- deterministic scheduler dispatcher
- provider transport contract tests

## 23B — App/API integration

Next.

- attach `SocialStore` to `AppRuntime`
- `/api/meta/status`
- `/api/meta/pages`
- `/api/meta/ad-accounts`
- project publication CRUD/queue endpoints
- scheduler tick endpoint plus safe internal periodic runner
- Unified Timeline events: publication.created/queued/published/failed
- project detail includes publications

## 23C — Distribution UX

- first-class `Distribución` workspace, not editor clutter
- Meta connection/readiness card
- Facebook Page / Instagram account selector
- copy/caption editor
- media choice from project renders/assets
- now / schedule controls with local timezone display
- publication calendar and state badges
- retry/cancel flow
- remote post id and error diagnostics

## 23D — Public Media Bridge

Instagram's server-side publishing flow requires a media URL reachable by Meta for image/Reel URL-based publication.

Build a provider abstraction rather than hard-code a storage vendor:

- `MediaBridge.publish(local_path) -> signed/public URL + expiry + sha256`
- verify object SHA-256 before queueing
- expiry must cover Meta ingest window
- automatic cleanup policy
- no project credential persistence

Until this gate exists, local Instagram files remain explicitly `not ready for publish` rather than silently failing.

## 23E — Paid Media

- ad account readiness and permissions diagnostics
- campaign draft model
- objectives use current `OUTCOME_*` naming
- special-ad-category declaration
- ad set targeting/budget validation
- creative from project publication/render
- create Campaign/AdSet/Creative/Ad in `PAUSED`
- preview estimated spend settings before any activation
- activation is separate, explicit and auditable
- insights ingestion after launch

## Later channels

Once the publication domain is stable, add adapters without changing the queue model:

- YouTube
- TikTok
- LinkedIn
- X where API/product constraints make sense
- optional WhatsApp campaign handoff (not unsolicited bulk messaging)

## Certification gates

### Gate A — Source

- unit tests Ubuntu + macOS
- no token strings in persisted fixtures
- compile source

### Gate B — Meta sandbox/test assets

- discover authorized Page
- discover linked professional Instagram account
- publish test Facebook Page post
- create and publish Instagram test media via real reachable URL
- create test campaign and assert `PAUSED`

### Gate C — FULL MAC regression

- existing arm64 + Intel editor/runtime smoke remains green
- social subsystem cannot change packaged Whisper/FFmpeg/editor guarantees

### Gate D — Real UAT

- connect user's Meta Business assets
- schedule publication
- restart app before due time
- publication executes once only
- failure is retryable and never duplicates a confirmed remote post
- paid campaign remains paused until explicit activation
