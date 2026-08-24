# Wave 96 · Prepare v0.9.0 Release Source

## Purpose

Wave 96 performs the one source mutation that must happen **before** release-bound physical UAT: it freezes the canonical product identity to the stable release intent that will later be tagged.

Canonical source becomes:

- product version: `0.9.0`;
- `RELEASE_READY=True`;
- `RELEASE_TAG="v0.9.0"`;
- W95 source state: `PREPARED_RELEASE`;
- runtime: Wave 76.

This is a source-contract transition only. It does not create a Git tag and it does not grant operational, release, publication, or production authority.

## Why preparation must precede UAT

W95 binds physical UAT to exact source identity. If version or tag intent were changed after UAT, the Git SHA and source digest would change and the prior UAT could not legitimately authorize the resulting release.

The correct sequence is therefore:

1. freeze stable version and canonical tag intent in source;
2. merge that source to `main`;
3. let the controlled `push` to `main` produce the exact eligible arm64 physical-UAT candidate;
4. execute real Phase A product UAT on Darwin arm64 outside CI;
5. execute the 12 Phase B release-operational manual gates;
6. finalize the W85 combined attestation carrying W95 prepared-source identity;
7. transport and verify that attestation through W86;
8. only then may a future tag event attempt the Developer ID, notarization, production-gate, W91, W92, W94 and W93 publication chain.

## Authority boundary

`RELEASE_READY=True` now means **source prepared for release-bound validation**, not “release already approved”.

Until the external gates exist, canonical source readiness must remain:

- `source_release_state=PREPARED_RELEASE`;
- `source_ready=true`;
- `stage=SOURCE_CONTRACT_READY`;
- `operational_inputs_complete=false`;
- `production_ready=false`.

The release-enablement audit must remain `AWAITING_OPERATIONAL_AUTHORIZATION` with all external runtime requirements false.

## Physical candidate boundary

The exact release-bound UAT candidate is still eligible only when built from a controlled GitHub Actions `push` to `refs/heads/main` on arm64.

A PR artifact remains validation-only. A tag artifact remains a source-equivalent distribution rebuild. Neither may be represented as the exact physical candidate.

## Preserved downstream gates

Wave 96 does not alter or bypass:

- W85 combined Phase A + Phase B attestation;
- W86 sanitized UAT transport;
- W87 Developer ID signing and notarization;
- W88 distribution rebuild separation;
- W91 cross-architecture release evidence authorization;
- W92 exact packaged ZIP Apple trust and artifact authorization;
- W94 GitHub OIDC/Sigstore provenance handoff;
- W93 transactional GitHub Release publication.

No release tag or GitHub Release is created by this wave.

## Merge gate

Merge only the exact final W96 head after:

- Canonical Source CI Ubuntu PASS;
- Canonical Source CI macOS PASS;
- FULL MAC arm64 validation PASS;
- Intel x86_64 current-runtime certification PASS;
- tag-only release jobs SKIPPED on PR;
- branch `behind_by=0` against `main`.

After merge, the new `main` arm64 artifact becomes the first candidate eligible for release-bound physical UAT under the prepared `0.9.0 / v0.9.0` identity.
