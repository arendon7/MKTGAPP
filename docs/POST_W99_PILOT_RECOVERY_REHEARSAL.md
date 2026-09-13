# Post-W99 Pilot Recovery Rehearsal

## Boundary

This increment is **post-W99 development only**. Canonical `main` remains frozen at W99 commit:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

It does not change the `0.9.0` candidate, does not create release authority, and is **not production** certification.

## Purpose

The month-long local pilot now has verified snapshots. This block proves that an operator can take the newest verified snapshot and exercise a recovery-shaped read in a disposable workspace without restoring over active MERCADEO APP data.

The rehearsal is deliberately narrower than a real restore:

1. reuse `PilotDataSafety.verify_snapshot()` as the existing snapshot-integrity authority;
2. reject a snapshot-directory symlink before the rehearsal reads it;
3. fingerprint the active authoritative data locally;
4. copy the verified snapshot into a new sibling temporary workspace outside the active `data_root`;
5. verify every copied byte against the existing manifest;
6. structurally read JSON, JSONL and SQLite files from the isolated copy only;
7. delete the temporary rehearsal workspace in `finally`;
8. fingerprint active data again and require an exact match before returning PASS.

The public result is minimized. It reports only status, counts and safety booleans. Filesystem paths, manifest hashes, credentials and file contents are never projected to the browser.

## Explicit operator action

The only new endpoint is:

`POST /api/pilot-data-safety/snapshots/<snapshot_id>/rehearse`

It requires the same explicit local operator header already used by Pilot Data Safety:

`X-Mercadeo-Operator: pilot-data-safety`

The browser exposes **Probar recuperación** inside the local backup experience. The action uses the latest listed snapshot and clearly states that active data is not replaced.

There is no automatic rehearsal, cadence, polling or background monitor.

## Non-authority / fail-closed rules

This increment does **not** provide:

- live restore;
- snapshot delete;
- overwrite of active `data_root`;
- provider reads or mutations;
- Meta or AI client initialization;
- publication, campaign or CRM mutation authority;
- scheduler/worker startup for the recovered copy;
- credential export;
- path/hash exposure.

A malformed snapshot, corrupted isolated copy, unreadable structured file, active-data drift or failed cleanup causes the rehearsal to fail closed.

## Recovery evidence schema

Successful rehearsal returns `binario.marketing.pilot-recovery-rehearsal.v1` with minimized evidence including:

- snapshot id;
- source verification passed;
- isolated copy completed and verified;
- structural file/read counts;
- active data unchanged;
- temporary workspace cleaned;
- `restore_performed: false`;
- `delete_performed: false`;
- `provider_reads: false`;
- `provider_mutations: false`;
- `workers_started: false`.

## Development chain

`serve-dev` advances to `service_post_w99_pilot_recovery_rehearsal_app` and continues extending the already merged Pilot Language Polish terminal. The canonical release `serve` path remains untouched.

The repository must continue to contain exactly these three canonical workflow files:

- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

Physical Apple Silicon UAT and W99 release authority remain separate from this post-W99 pilot evidence.
