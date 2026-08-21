# Wave 77 · Physical UAT contract fix

Wave 77 is a narrow release-readiness hotfix. It does not add a marketing feature and does not satisfy physical UAT automatically.

## Defect corrected

W69 exposes the canonical physical-UAT preflight flag as `ready_to_begin_physical_uat`. W71 was reading the stale key `ready_for_physical_uat`, which could make the candidate certification dossier report `BLOCKED_PREFLIGHT` even when the physical Mac/build preflight was actually ready.

## W77 contract

- W71 now reads `ready_to_begin_physical_uat`.
- A regression test exercises the corrected contract through the current W76 runtime.
- `RELEASE_READY` remains `False`.
- Version remains `0.9.0.dev1`.
- No provider action, publication, paid activation, AI action or business mutation is added.
- Physical UAT still requires explicit human execution on the exact eligible Mac arm64 build.
- The dossier remains read-only and is not release authority.

## Next gate

After source CI and the exact Mac build are green, execute the W76 sandbox journey to 6/6 and then perform the guided physical UAT on that exact build. Only manually recorded eligible evidence may remove the physical-UAT blocker.
