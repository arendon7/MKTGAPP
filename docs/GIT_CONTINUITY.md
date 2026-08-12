# Git continuity and release retention

`arendon7/MKTGAPP` is the canonical source of BINARIO Marketing App.

## What is permanent

- Every coherent change is committed to Git.
- `main` is the stable integration branch.
- Feature work happens on branches and enters through tested pull requests.
- Version tags (`v*`) identify immutable release commits.
- GitHub Releases created from those tags hold the certified Mac ZIPs and SHA-256 files persistently, in addition to GitHub's source archives for the tag.

## What is disposable

- local build folders;
- local `.app`/ZIP copies;
- Actions artifacts used during ordinary CI;
- caches;
- temporary runtime downloads.

None of those disposable objects may be the only copy of source or the only record of an accepted release.

## Release flow

1. merge a fully green change to `main`;
2. create an annotated/immutable `v*` tag at the accepted main SHA;
3. `Persistent Mac Release` builds arm64 and x86_64 natively;
4. each bundle is audited and smoke-booted;
5. the workflow creates architecture-specific ZIPs, SHA-256 files and machine-readable release manifests;
6. a GitHub Release is created only if both architectures pass and both checksums verify.

If one architecture fails, no release is published.
