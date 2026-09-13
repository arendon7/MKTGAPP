# Post-W99 · Pilot Data Safety

Status: **pilot development / not production**.

Frozen release baseline remains `main` at W99:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

This increment is available only through the evolving `serve-dev` chain. It does not change canonical `serve`, W99 release authority, physical Apple Silicon UAT, tags or GitHub Releases.

## Purpose

The month-long local pilot now has an explicit operator-controlled way to create and verify local snapshots of MERCADEO APP data before broader restore/recovery authority is introduced.

This phase deliberately supports only:

- list local snapshots;
- create a snapshot after an explicit operator click;
- verify a snapshot against its internal SHA-256 manifest.

**Restore and delete are intentionally unavailable.** A restore workflow changes authoritative application state and requires a separate offline/quiescence design before it is safe to expose.

## Source of truth

The application `data_root` remains the only live source of truth. By default it is the local MERCADEO APP/Binario data directory resolved by the existing runtime, with `BINARIO_IA_HOME` respected where already supported.

Snapshots are copies only. The runtime never reads business state from the backup directory.

The backup directory is a sibling of `data_root`, named `<data_root name> Backups`, so it cannot recurse into itself.

## Included data

The snapshot walks the complete durable `data_root`, preserving the existing stores and managed files rather than inventing a second schema. This includes, where present, project assets, company/media state, CRM, creative workflow, campaigns, paid-media state, social/publication state, Inbox-related local state, editor/workspace state, renders/transcriptions and other durable files managed below `data_root`.

The snapshot mechanism does not interpret or rewrite those stores.

## Excluded transient data

The following are excluded deliberately:

- directories named `temp`;
- directories named `logs`;
- hidden files;
- `.part` files;
- temporary siblings produced by atomic JSON writes (`*.json.<temporary>`).

These exclusions prevent in-flight/transient artifacts from being mistaken for authoritative pilot state.

## Credentials

Provider credentials are not copied by the snapshot mechanism.

The existing Meta and AI credential authorities resolve secrets from environment variables or the macOS Keychain. They do not persist access tokens/API keys inside `data_root`. Snapshot API responses also never expose file paths, per-file hashes, provider credentials or raw manifest inventory.

## Consistency contract

Every snapshot is fail-closed:

1. scan the included source inventory using relative path, byte size and nanosecond modification time;
2. reject symlinks in included application data;
3. copy each regular file while computing SHA-256;
4. verify that each source file still matches the initial metadata after its copy;
5. rescan the complete included source inventory;
6. abort and remove the temporary snapshot if the inventory changed;
7. write the manifest only after the source inventory is stable;
8. verify all copied bytes against the manifest;
9. atomically rename the completed temporary snapshot into its final local snapshot directory.

A failed or changing source never produces a completed snapshot entry.

This provides a bounded local consistency check without pausing provider workers or claiming distributed/transactional backup semantics.

## HTTP/API boundary

Local development endpoints:

- `GET /api/pilot-data-safety/snapshots`
- `POST /api/pilot-data-safety/snapshots`
- `POST /api/pilot-data-safety/snapshots/<snapshot_id>/verify`

Mutation endpoints require the explicit browser header:

`X-Mercadeo-Operator: pilot-data-safety`

The browser sends it only from explicit snapshot/verification controls. The feature adds no background polling, `MutationObserver`, automatic snapshot cadence, provider read, provider write, publish action, campaign activation, CRM mutation or AI execution.

## Public projection

The UI/API may expose only minimized snapshot metadata:

- snapshot id;
- creation timestamp;
- file count;
- total bytes;
- transient-exclusion description;
- verification result for the explicit operation;
- `restore_available=false`;
- `credentials_included=false`.

Per-file relative paths and SHA-256 values exist only inside the local manifest used for verification and are not serialized to the browser list projection.

## Operator UX

`serve-dev` adds **Respaldo local** to the pilot shell. Opening it performs a local list read. Creating or verifying requires a direct button click. The panel states clearly that snapshots stay local and that restore/delete are not available in this phase.

## Release separation

The repository must continue to contain exactly these workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

This increment does not authorize a production release, `v0.9.0`, provider delivery claim or physical-UAT claim.
