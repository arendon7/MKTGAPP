# Wave 81 · Main Physical UAT Candidate

Wave 81 closes the provenance ambiguity between a pull-request validation bundle and the exact bundle eligible for physical UAT.

## Problem corrected

GitHub pull-request workflows build a synthetic merge ref. That tree can be identical to the final `main` tree, but physical-UAT and release evidence are intentionally SHA-bound. A PR artifact must therefore never be mistaken for the physical-UAT candidate.

## W81 contract

- `BUILD_PROVENANCE.json` records `build_event`, `build_ref` and `physical_uat_candidate`.
- `physical_uat_candidate=true` is emitted only when the bundle is built by a GitHub Actions `push` on `refs/heads/main`.
- Pull-request, workflow-dispatch, local and tag builds remain `physical_uat_candidate=false`.
- W69 preflight adds the required `main-candidate-build` gate.
- Starting, updating or finishing physical-UAT evidence is rejected server-side whenever preflight is blocked.
- An active session is only offered as continuable when the current bundle still passes preflight.
- The arm64 current-build guard executes the W81 provenance audit on every build.

## Preserved boundaries

- Current product runtime remains W76.
- W80 x86_64 certification remains valid and does not gain physical-UAT authority.
- Physical UAT remains arm64-only, explicit and human-operated.
- Version remains `0.9.0.dev1`.
- `RELEASE_READY=False` and `RELEASE_TAG=None` remain unchanged.
- No release, notarization, provider mutation, publication, paid-media activation or AI execution is enabled.
- Exactly three canonical GitHub workflows remain.

## Next gate

After W81 passes source CI, FULL MAC arm64 and the existing Intel current-runtime certification, merge it to `main`. The push-to-main arm64 bundle produced from that merge becomes the only eligible physical-UAT candidate. On the physical Mac, W76 sandbox progress must reach 6/6 before the guided physical-UAT scenarios are recorded on that exact build.
