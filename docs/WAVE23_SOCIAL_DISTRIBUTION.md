# Wave 23 — Social Distribution, Meta Publishing and Ads

## Goal

Extend BINARIO Marketing from content creation into controlled distribution without weakening the certified local editor/runtime.

## Non-negotiable contracts

1. Provider credentials never enter project JSON, artifact metadata, logs, browser state, or timeline payloads.
2. Social publication is durable and auditable: `DRAFT -> QUEUED -> PUBLISHING -> PUBLISHED|FAILED`.
3. Scheduled work persists across app restarts. While the desktop service is alive, due jobs execute automatically; overdue jobs remain durable and process after the next launch.
4. A local file is never represented as publishable Instagram media unless the selected Meta flow can actually ingest it.
5. Paid media creation defaults to `PAUSED`; activation/spend is a separate explicit gate.
6. Provider adapters remain isolated from editor/render code.
7. Every external provider call is testable through an injectable transport.
8. Managed render publication is fail-closed: project scope, render status, media constraints, byte size and SHA-256 are verified before upload.

## 23A — Distribution core

Status: implemented.

- durable publication store
- timezone-aware queue and due selection
- restart recovery for interrupted publication attempts
- Meta Graph API client
- Facebook Page discovery and sanitized Page token handling
- Instagram professional-account discovery through linked Pages
- Facebook text/link/image publishing primitives
- Instagram image/Reel URL container + processing + publish primitives
- Meta ad account discovery
- campaign creation forced to `PAUSED`
- deterministic scheduler dispatcher
- provider transport contract tests

## 23B — App/API integration

Status: implemented.

- `SocialStore` attached to `AppRuntime`
- `/api/meta/status`
- `/api/meta/pages`
- `/api/meta/ad-accounts`
- project publication create/list/queue/publish-now/cancel endpoints
- safe internal periodic scheduler while desktop service is alive
- manual run-due endpoint for controlled execution
- Unified Timeline events for publication lifecycle
- project detail includes publications
- Meta campaign endpoint forced to `PAUSED`

## 23C — Distribution UX

Status: implemented.

- first-class `Distribución` workspace isolated from editor code
- Meta connection/readiness card
- Facebook Page / Instagram account selector
- copy/caption editor
- now / schedule controls with UTC persistence
- publication queue with state, attempts, remote ID, errors and retry/cancel actions
- ad-account selector
- campaign objective and special-category controls
- explicit `PAUSED` campaign behavior

## 23D — Local Facebook Reel publishing

Status: implemented in source and under CI certification.

A completed managed project render can be selected directly in Distribution and streamed to Meta without a CDN or a duplicate upload file.

Contracts:

- Facebook Page only
- publication stores `render_id`, never an absolute filesystem path
- render must belong to the same project
- render status must be `PASS`
- exact 9:16
- minimum 540x960
- duration 4–60 seconds
- output must remain inside the managed project `exports` directory
- recorded byte size must still match
- recorded SHA-256 must still match
- binary upload streams from disk in chunks rather than reading the whole video into memory
- Page access token remains in process memory only
- flow: initialize Reel upload -> binary upload -> finish as `PUBLISHED`

## 23E — Instagram local media bridge

Next.

The currently certified Instagram path remains URL-based. Local Instagram media is explicitly blocked rather than pretending it can publish.

Options to certify before enabling:

- Meta-supported resumable binary upload if its production contract is validated end-to-end for our account flow, or
- `MediaBridge.publish(local_path) -> reachable URL + expiry + sha256`

Requirements:

- verify source SHA-256
- no project credential persistence
- expiry covers Meta ingest window
- deterministic cleanup
- one-click path from project render to Instagram publication

## 23F — Meta connection hardening

Next.

- user-facing Meta OAuth flow
- secure native credential persistence through macOS Keychain abstraction
- token expiry/refresh diagnostics
- permission/readiness diagnostics per Page, Instagram account and ad account
- disconnect/reconnect without project mutation

The current provider foundation accepts `META_ACCESS_TOKEN` from process environment so publishing logic can be certified without storing credentials in project data.

## 23G — Paid Media

Current status: Campaign creation only, always `PAUSED`.

Next:

- ad-account readiness and permission diagnostics
- campaign draft model
- objectives use current `OUTCOME_*` naming
- special-ad-category declaration
- Ad Set targeting/budget validation
- creative from project publication/render
- create Campaign/AdSet/Creative/Ad in `PAUSED`
- preview budget/spend settings before activation
- activation is separate, explicit and auditable
- insights ingestion after launch

## 23H — Always-on scheduling

Optional later gate if jobs must execute while the desktop app is fully closed:

- macOS launchd helper or equivalent background service
- same durable publication queue; no second scheduling database
- single-instance guard
- wake/retry policy and offline diagnostics

Until this gate, queued work survives closure and overdue jobs execute after the next app launch.

## Later channels

Once the publication domain is stable, adapters can reuse the same queue model:

- YouTube
- TikTok
- LinkedIn
- X where API/product constraints make sense
- optional WhatsApp campaign handoff, excluding unsolicited bulk messaging

## Certification gates

### Gate A — Source

- unit tests Ubuntu + macOS
- browser JavaScript syntax
- no credential persistence
- compile source

### Gate B — Meta sandbox/test assets

- discover authorized Page
- publish test Facebook Page post
- publish a certified local Facebook Reel
- discover linked professional Instagram account
- publish Instagram test media through a certified ingest path
- create test campaign and assert `PAUSED`

### Gate C — FULL MAC regression

- arm64 bundle build/audit/smoke PASS
- Intel bundle build/audit/smoke PASS
- Whisper/FFmpeg/editor guarantees unchanged

### Gate D — Real UAT

- connect actual Meta Business assets
- publish a local project Reel
- schedule a publication
- restart app before due time and confirm durable recovery
- failure is retryable and never silently duplicates a confirmed remote post
- paid campaign remains paused until explicit activation
