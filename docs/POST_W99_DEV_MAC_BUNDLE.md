# Post-W99 · Isolated Development macOS Bundle

## Purpose

Package the evolving post-W99 product line into a real macOS application without changing, replacing or re-signing the frozen W99 release candidate.

## Distinct product identity

Development app:

`Binario Marketing IA Post-W99 Dev.app`

Bundle identifier:

`com.sistemabinario.marketing.postw99dev`

Default output:

`dist-post-w99/`

The inherited native executable name remains an internal bundle implementation detail; Finder/product identity is explicitly development-only.

## Runtime

The builder reuses the already-certified embedded runtime assembly for Python, FFmpeg, Whisper and the Meta Keychain helper, then replaces only the launch terminal with:

`binario_marketing.service_post_w99_dev_app`

This makes the packaged app exercise the actual cumulative post-W99 chain, including Primary Navigation and the Calendar background scheduler control.

## Non-authority provenance

Every bundle contains `POST_W99_DEV_BUILD.json` with:

- exact source Git SHA;
- architecture;
- development bundle identifier;
- post-W99 terminal;
- frozen canonical W99 SHA;
- `release_authority: false`;
- `physical_uat_authority: false`;
- `w100: false`.

This file exists specifically to prevent a development artifact from being interpreted as a release candidate.

## Dedicated CI

`.github/workflows/post-w99-dev-mac.yml` is independent of the canonical release workflows. On relevant pull requests it:

1. builds the isolated arm64 development app;
2. audits its development-only identity and provenance;
3. launches the packaged post-W99 terminal on loopback;
4. verifies health, Primary Navigation and Calendar background-status surfaces;
5. verifies that merely launching/status-reading does not install a LaunchAgent;
6. uploads a short-retention development ZIP for controlled testing.

It does not run publication transactions, release gates, tag creation or release publication.

## Boundary

Canonical `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` remains untouched.

The canonical `dist/Binario Marketing IA.app` path and existing W99 release builders remain unchanged.

This development bundle is not a Physical-UAT candidate and **No es W100**.
