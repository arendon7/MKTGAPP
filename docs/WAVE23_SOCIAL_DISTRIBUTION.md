# Wave 23 — Social Distribution, Meta Publishing and Ads

## Goal

Extend BINARIO Marketing from content creation into controlled distribution without weakening the certified local editor/runtime.

## Non-negotiable contracts

1. Provider credentials never enter project JSON, artifact metadata, logs, browser storage, or timeline payloads.
2. Social publication is durable and auditable: `DRAFT -> QUEUED -> PUBLISHING -> PUBLISHED|FAILED`.
3. Scheduled work persists across app restarts. While the desktop service is alive, due jobs execute automatically; overdue jobs remain durable and process after the next launch.
4. A local file is never represented as publishable Instagram media unless the selected Meta flow can actually ingest it.
5. Paid media creation is fail-closed: Campaign, Ad Set and Ad are created `PAUSED`; activation/spend is a separate explicit gate.
6. Provider adapters remain isolated from editor/render code.
7. Every external provider call is testable through injectable transports.
8. Managed render publication verifies project scope, render status, media constraints, byte size and SHA-256 before upload.
9. Confirmed remote paid-media IDs are checkpointed in order so retries resume instead of duplicating confirmed objects.

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
- Unified Timeline publication events
- project detail includes publications and paid-media drafts
- certified legacy HTTP server preserved as `service_core.py`; Wave 23 extension routes live in the thin `service.py` layer

## 23C — Distribution UX

Status: implemented in source; current head remains subject to CI/FULL MAC gates.

- first-class `Distribución` workspace isolated from editor code
- Meta connection/readiness card
- Facebook Page / Instagram account selector
- copy/caption editor
- now / schedule controls with UTC persistence
- publication queue with state, attempts, remote ID, errors and retry/cancel actions
- local Facebook Reel selector
- Meta connection/disconnection controls
- full paid-media draft form and resumable `PAUSED` creation controls

## 23D — Local Facebook Reel publishing

Status: implemented.

A completed managed project render can be selected directly in Distribution and streamed to Meta without a CDN or duplicate upload file.

Contracts:

- Facebook Page only
- publication stores `render_id`, never an absolute filesystem path
- render belongs to the same project
- render status is `PASS`
- exact 9:16
- minimum 540x960
- duration 4–60 seconds
- output remains inside managed project `exports`
- recorded byte size still matches
- recorded SHA-256 still matches
- upload streams from disk in chunks
- Page access token remains in process memory only
- flow: initialize Reel upload -> binary upload -> finish as `PUBLISHED`

## 23E — Instagram local media bridge

Next.

The currently implemented Instagram path remains URL-based. Local Instagram media is explicitly blocked rather than pretending it can publish.

Candidate gates:

- certify Meta-supported resumable binary upload end-to-end for our account flow, or
- build `MediaBridge.publish(local_path) -> reachable URL + expiry + sha256`

Requirements:

- verify source SHA-256
- no project credential persistence
- expiry covers Meta ingest window
- deterministic cleanup
- one-click path from project render to Instagram publication

## 23F — Meta connection and native secret storage

Status: source implementation complete; FULL MAC native certification pending on the current head.

Implemented:

- `MetaCredentialStore`: development fallback from `META_ACCESS_TOKEN`, native Keychain otherwise
- Swift helper using Security.framework `SecItem*`
- data-protection Keychain query
- helper receives secrets through stdin, never process argv
- helper bundled per native architecture by FULL MAC builder
- FULL MAC auditor requires and exercises helper status
- token validation through Meta `/me` before persistence
- CLI: `meta-status`, `meta-connect`, `meta-disconnect`
- browser POST/DELETE `/api/meta/connection`
- UI password field clears immediately after the connection attempt
- status exposes source/readiness only, never token value
- environment-controlled connections cannot be overwritten or deleted by the UI

Still next:

- user-facing Meta OAuth rather than manual access-token paste
- token expiry/refresh diagnostics
- granular permission/readiness diagnostics per Page, Instagram account and ad account

## 23G — Paid Media

Status: Campaign + Ad Set + Creative + Ad source/API/UI implemented; current head remains subject to CI/FULL MAC gates.

Implemented:

- durable project-scoped paid-media draft store
- credentials rejected from draft state
- campaign objectives use `OUTCOME_*`
- special-ad-category declaration
- Ad Set budget, age and geo validation
- HTTPS validation for link/picture creative assets
- CTA allowlist
- Campaign creation forced `PAUSED`
- Ad Set creation forced `PAUSED`
- Ad Creative creation without activation state
- Ad creation forced `PAUSED`
- ordered remote checkpoints: Campaign -> Ad Set -> Creative -> Ad
- retries resume after the last confirmed remote object
- local draft cancellation is blocked once a remote Meta object exists, requiring explicit review
- Distribution UI supports save-draft, create-complete-paused and resume-paused actions
- no activation endpoint or activation button

Next after real Meta UAT:

- permissions/readiness diagnostics
- budget/currency interpretation guidance from the selected ad account
- additional creative types based on project renders
- preview and validation of placements
- insights ingestion after launch
- activation remains a separate explicit, auditable future gate

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

- validate/store connection through native Keychain
- discover authorized Page
- publish test Facebook Page post
- publish certified local Facebook Reel
- discover linked professional Instagram account
- publish Instagram test media through a certified ingest path
- create Campaign + Ad Set + Creative + Ad and assert all activatable levels are `PAUSED`
- interrupt after one confirmed remote object and verify retry resumes without duplicate creation

### Gate C — FULL MAC regression

- arm64 bundle build/audit/smoke PASS
- Intel bundle build/audit/smoke PASS
- native Keychain helper compiles/runs for both architectures
- Whisper/FFmpeg/editor guarantees unchanged

### Gate D — Real UAT

- connect actual Meta Business assets
- publish a local project Reel
- schedule a publication
- restart app before due time and confirm durable recovery
- failure is retryable and never silently duplicates a confirmed remote post
- paid-media hierarchy remains paused until an explicitly separate activation gate
