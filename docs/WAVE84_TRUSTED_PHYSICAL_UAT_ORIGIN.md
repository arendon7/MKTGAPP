# Wave 84 · Trusted Physical UAT Origin

Wave 81 bound physical UAT evidence to the exact arm64 W76 candidate. Wave 82 hard-stopped release publication until production UAT evidence is explicitly consumed. Wave 83 corrected the externally delivered arm64 artifact identity. Wave 84 closes the remaining ambiguity: an arm64 validation build must not be usable as physical-UAT evidence merely because it contains the same source tree.

## W84 contract

`PHYSICAL_UAT_CANDIDATE.json` now records `build_origin` and derives one of two immutable roles:

- `PHYSICAL_UAT_CANDIDATE_ONLY` for controlled GitHub Actions `push` builds on `refs/heads/main` or version tags `refs/tags/v*`;
- `VALIDATION_BUILD_ONLY` for pull requests, workflow dispatch, local builds or any other origin.

The role is derived from `GITHUB_EVENT_NAME` and `GITHUB_REF`; verification re-derives trust from the recorded origin and rejects tampered trust metadata.

The W83 external ZIP filename remains stable for workflow compatibility, but `PHYSICAL_UAT_CANDIDATE.json` and `FULL_MAC_DELIVERY.json` are authoritative. Delivery metadata now includes role, build origin and `physical_uat_eligible`.

## Enforcement

The same trusted-origin condition is required by:

1. W69 in-app physical-UAT preflight;
2. start/update/finish physical-UAT mutations;
3. `collect_release_uat.py`;
4. `release_candidate_gate.py`;
5. W84 bundle audit;
6. the W83 current-arm64 packager.

Therefore a PR artifact can be fully built, audited and smoke-tested while remaining `VALIDATION_BUILD_ONLY`; it cannot begin or satisfy physical UAT. After merge, the `push main` build becomes the eligible physical candidate for its exact SHA.

## Boundaries preserved

- product runtime remains Wave 76;
- certification guard is Wave 84;
- W82 publication hard stop remains active;
- W83 exact-current arm64 delivery remains active;
- x86_64 remains distribution-certified but not physical-UAT eligible;
- `0.9.0.dev1`;
- `RELEASE_READY=False`;
- `RELEASE_TAG=None`;
- no automatic UAT PASS;
- sandbox is not release evidence;
- no provider, publication, paid-media or AI mutation;
- exactly three canonical workflows.

## Next gate

After W84 is certified and merged, use only the exact post-merge `main` arm64 artifact whose manifest reports `PHYSICAL_UAT_CANDIDATE_ONLY`, `physical_uat_eligible=true`, the final `main` SHA and matching source/manifest hashes. Then complete controlled sandbox 6/6 and guided physical UAT on the real arm64 Mac. Developer ID signing, notarization and production version/tag remain independent later gates.
