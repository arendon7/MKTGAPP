# Post-W99 · Continuous Local Social Scheduler

## Purpose

Allow already-approved, already-queued Facebook and Instagram publications to execute at their scheduled time on macOS even when the Binario Marketing web interface is closed.

This increment reuses the existing durable social queue and Meta publisher. It does not create a second publication system.

## Architecture

The background path is deliberately short-lived:

1. macOS `launchd` starts a one-shot worker every 60 seconds;
2. the worker uses the Python 3.12 runtime embedded in `Binario Marketing IA.app`;
3. the worker reads the existing Meta token through the native macOS Keychain helper;
4. it opens the existing `State/social` durable queue;
5. it obtains the cross-process publication lock introduced by the prior post-W99 increment;
6. only after owning that lock may it recover an interrupted `PUBLISHING` row;
7. it processes due `QUEUED` publications with the existing `MetaSocialPublisher`;
8. publication results are written to the existing workspace timeline;
9. the worker records a secret-free execution receipt under `State/social-background/status.json` and exits.

There is no permanent Python daemon.

## Why one-shot instead of another server

A periodic one-shot worker has a smaller operational surface than a second always-running application process:

- no extra HTTP server or port;
- no duplicate UI runtime;
- no long-lived in-memory state;
- process crashes release the kernel publication lock;
- `launchd` owns retry/lifecycle behavior;
- app and worker safely contend for the same queue without duplicate sends.

## Explicit opt-in

Background execution is **not enabled automatically** by installing or opening the application.

Available CLI controls:

- `social-worker-once`
- `social-background-status`
- `social-background-install`
- `social-background-uninstall`

`social-background-install` creates a per-user LaunchAgent only after explicit invocation. The generated plist contains paths and runtime configuration only; it never contains `META_ACCESS_TOKEN` or any provider credential.

## LaunchAgent contract

Label:

`com.sistemabinario.marketing.social-scheduler`

Default interval:

`60 seconds`

The LaunchAgent references:

- the embedded Python executable inside the selected app bundle;
- a small generated worker bootstrap under `~/Library/Application Support/Binario Marketing IA/`;
- the native `binario-meta-keychain` helper inside the app bundle;
- optional `BINARIO_IA_HOME` only when the operator has explicitly configured a non-default data home.

Logs are written under:

`~/Library/Application Support/Binario Marketing IA/Logs/`

## App movement/update behavior

The LaunchAgent intentionally references the exact app bundle from which it was installed. If the app is moved or replaced at another path, `social-background-status` reports the installation as stale and the operator can reinstall the background integration from the current bundle.

No credential migration is necessary because the token remains in Keychain.

## Queue safety

Desktop and background execution share the same kernel-backed publication lock.

If the desktop application is already publishing, the background worker returns `BUSY` and exits without mutating the queue.

If a previous publisher crashed, recovery is allowed only after the worker obtains the process lock. A recovered `PUBLISHING` publication becomes `FAILED` with the existing manual-remote-review safeguard instead of being retried blindly.

## Worker execution states

The secret-free run receipt may report:

- `OK`: cycle completed, including a cycle with zero due publications;
- `BUSY`: another local process owns the publication queue;
- `NO_CREDENTIALS`: Meta is not currently connected;
- `ERROR`: the worker could not complete a safe cycle.

## Deliberate non-scope

This increment does not:

- queue or approve content automatically;
- generate content with AI automatically;
- publish drafts that were not explicitly queued;
- activate Meta campaigns;
- modify company-to-Meta account bindings;
- store Meta credentials in files;
- create a cloud scheduler;
- guarantee execution while the Mac is powered off;
- change canonical `main` or the frozen W99 physical candidate.

When the Mac is sleeping or powered off, `launchd` execution depends on macOS lifecycle behavior; this is a local scheduler, not a cloud delivery SLA.

## Frozen release boundary

Canonical `main` remains frozen at:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

This is a post-W99 development increment. **No es W100.** It grants no Physical-UAT PASS, release authority, publication approval authority or production-ready status.
