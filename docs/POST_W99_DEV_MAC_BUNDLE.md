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

The builder reuses the existing embedded runtime assembly for Python, FFmpeg, Whisper and the Meta Keychain helper, then replaces only the launch terminal with:

`binario_marketing.service_post_w99_dev_app`

This makes the packaged app exercise the cumulative post-W99 chain, including Primary Navigation and the Calendar background scheduler control.

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

## Workflow boundary

The repository intentionally remains at the canonical three-workflow topology:

- `ci.yml`;
- `full-mac-app.yml`;
- `release-mac.yml`.

No fourth post-W99 workflow is added. This preserves the historical W99 workflow guard and avoids silently changing release topology.

The development bundle is built through the explicit script:

`scripts/build_post_w99_dev_mac_app.sh`

and verified with:

`scripts/audit_post_w99_dev_mac_app.sh`

The source contracts for both scripts are covered by the canonical test suite. A controlled Mac execution can build and boot this development-only app without changing the release candidate or release workflows.

## Boundary

Canonical `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` remains untouched.

The canonical `dist/Binario Marketing IA.app` path and existing W99 release builders remain unchanged.

This development bundle is not a Physical-UAT candidate and **No es W100**.
