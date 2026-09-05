# Post-W99 · Social Scheduler Process Lock

## Purpose

Prepare the existing durable Meta publication queue for a later optional background scheduler without creating duplicate Facebook or Instagram publications when more than one local process can see the same queue.

## Problem closed by this increment

Before this change, `SocialStore` serialized threads inside one Python process only. Two independent processes could both observe the same `QUEUED` publication before either transitioned it to `PUBLISHING`, which could cause duplicate remote sends.

A second process could also call startup recovery while the first process was legitimately publishing and incorrectly convert that live `PUBLISHING` row to `FAILED`.

## Contract

The shared social root now owns a kernel-backed, non-blocking lock file:

`.publish-due.lock`

The file contains no credential, publication or operator data. File existence does not indicate ownership; the operating-system lock does. A process crash releases the kernel lock automatically.

The lock protects:

- explicit `MetaSocialPublisher.publish()`;
- scheduled `MetaSocialPublisher.run_due()`;
- scheduler startup `recover_interrupted()`.

When another process owns the queue:

- scheduled ticks fail closed and return no work without mutating rows;
- explicit publish fails closed with a queue-busy error;
- startup recovery skips recovery rather than touching a potentially live publication.

## Platform behavior

- macOS/Linux use `flock(LOCK_EX | LOCK_NB)`;
- Windows source/dev compatibility uses `msvcrt` non-blocking byte locking;
- an unsupported platform fails closed instead of claiming multi-process safety.

## Deliberate non-scope

This increment does **not**:

- install a LaunchAgent;
- start a new background process;
- change publication schedules;
- create a cloud worker;
- add Meta credentials to files or service definitions;
- change company-to-Meta account bindings;
- change publication authority or campaign authority;
- change `main` or the W99 candidate.

A continuous local scheduler can be considered only after this process-safety prerequisite is certified.

## Frozen release boundary

Canonical `main` remains frozen at:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

This post-W99 development increment is **No es W100**. It grants no Physical-UAT PASS, release authority, publication authority or production-ready status.
