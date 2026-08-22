# Wave 82 · Trusted Physical UAT Origin

Wave 82 closes the operational gap left after the exact-candidate hardening in W81: an arm64 pull-request artifact can be cryptographically valid and source-identical to a later merge, but it must never be mistaken for the physical-UAT candidate.

## W82 contract

- `PHYSICAL_UAT_CANDIDATE.json` now records `build_origin.event`, `build_origin.ref` and `build_origin.trusted_for_physical_uat`.
- A controlled GitHub Actions `push` to `refs/heads/main` is a trusted physical-UAT origin.
- A controlled GitHub Actions `push` to a version tag `refs/tags/v*` is also trusted so a future final release candidate is not structurally unable to undergo physical UAT.
- Pull-request, local and workflow-dispatch builds are `VALIDATION_BUILD_ONLY` and set `eligible_build_origin=false`.
- W81 source/manfiest digests, codesign binding, runtime Wave 76 and exact Git-SHA evidence remain authoritative.

## Server-side enforcement

W69 physical preflight now requires the trusted candidate manifest in addition to the physical arm64 Mac, provenance, runtime and fail-closed release checks.

Starting, updating or finishing a physical-UAT session is rejected server-side while preflight is blocked. Therefore a PR artifact cannot create physical evidence even if manually copied to a real arm64 Mac.

## Release evidence enforcement

`collect_release_uat.py` and `release_candidate_gate.py` require:

- role `PHYSICAL_UAT_CANDIDATE_ONLY`;
- trusted push origin (`main` or version tag `v*`);
- `eligible_build_origin=true`;
- exact Git SHA, source SHA-256 and candidate-manifest SHA-256;
- real non-CI Darwin arm64 host for evidence collection.

## Preserved boundaries

- Product runtime remains Wave 76.
- Version remains `0.9.0.dev1`.
- `RELEASE_READY=False` and `RELEASE_TAG=None` remain unchanged.
- No automatic UAT PASS.
- Synthetic W75/W76 sandbox is not release evidence.
- W80 Intel remains distribution-certified but is not physical-UAT eligible.
- No provider, publication, paid-media or AI mutation is added.
- Exactly three canonical GitHub workflows remain.

## Next gate

After source CI, FULL MAC arm64 and native Intel certification are green, merge W82. The arm64 artifact produced by the resulting `push` to `main` is the exact build to hand to the physical Mac operator. Complete the W76 sandbox to 6/6, then record guided physical UAT against that exact bundle.
