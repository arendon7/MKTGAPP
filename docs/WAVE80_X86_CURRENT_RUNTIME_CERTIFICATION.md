# Wave 80 · x86_64 Current Runtime Certification

Wave 79 made x86_64 fail closed rather than allowing Persistent Release to fall back to the historical W45 runtime. Wave 80 adds a real Intel certification path for the same current W76 product chain.

## W80 contract

- x86_64 release candidates must replay the canonical `build_full_mac_current.sh` chain, changing only its architecture guard at execution time.
- The replay refuses to run if the canonical guard drifts, so there is no copied or independently maintained wave chain to silently diverge.
- The resulting Intel bundle must contain `service_wave76_app import serve` and pass W78/W79/W80 certification guards.
- A native `macos-15-intel` pull-request job builds, audits and smoke-boots the exact x86_64 current runtime.
- Persistent release continues to build both arm64 and x86_64 through `build_full_mac_release_candidate.sh`; direct fallback to `build_full_mac_app.sh` remains forbidden.

## Physical-UAT boundary

Intel certification does not widen the physical-UAT authority. W69 deliberately requires an arm64 physical build. W80 therefore verifies that an x86_64 bundle reports `arm64-build` as a preflight blocker, remains `BLOCKED_PREFLIGHT`, and cannot become production-ready from Intel certification alone.

## Release boundary

- `0.9.0.dev1`
- `RELEASE_READY=False`
- `RELEASE_TAG=None`
- no release tag created
- no notarization claim
- no automatic physical-UAT PASS
- no provider, publication, paid-media or AI mutation

A future release can only proceed after the canonical version contract is intentionally opened and the independent arm64 physical-UAT gate is satisfied.
