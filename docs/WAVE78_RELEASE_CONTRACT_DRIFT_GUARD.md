# Wave 78 · Release Contract Drift Guard

Wave 78 hardens the release-readiness chain after the W77 hotfix exposed a cross-wave contract drift between W69 and W71.

## Defect class addressed

W69 publishes the canonical preflight flag `ready_to_begin_physical_uat`. W71 previously consumed the stale key `ready_for_physical_uat`, and the historical W71 bundle audit did not assert that producer/consumer contract. W77 corrected the source defect; W78 makes that class of mismatch a failing bundle gate.

## W78 contract

- The packaged W69 producer must expose `ready_to_begin_physical_uat`.
- The packaged W71 consumer must read `ready_to_begin_physical_uat` and must not read `ready_for_physical_uat`.
- The current packaged W76 runtime must report `READY_FOR_PHYSICAL_UAT` when the canonical W69 contract is true.
- A stale-key-only preflight must fail closed as `BLOCKED_PREFLIGHT`.
- The W75 synthetic sandbox must remain unable to record physical-UAT release evidence.
- `0.9.0.dev1`, `RELEASE_READY=False`, no release tag, and exactly three canonical workflows remain unchanged.
- The guard performs no provider action, publication, paid activation, AI generation, release mutation or physical-UAT PASS recording.

## Build integration

The current arm64 builder executes the W78 drift guard after the already-certified W76 sandbox journey audit. W78 does not introduce a new runtime service or replace W76 as the current product runtime; it is a certification guard over the packaged source/runtime chain.

## Next gate

After Source CI and FULL MAC arm64 are green for this exact tree, run the W76 functional sandbox journey to 6/6 on the exact build, then execute guided physical UAT on an eligible real Mac arm64. Only explicit human evidence from that exact build may satisfy the physical-UAT blocker.
