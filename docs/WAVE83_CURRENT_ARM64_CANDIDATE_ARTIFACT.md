# Wave 83 · Current arm64 Candidate Artifact

## Purpose

Wave 83 removes the obsolete external Wave 47 identity from the canonical FULL MAC arm64 delivery. Wave 47 remains a historical product-surface layer and its audit is preserved, but it is no longer presented as the identity of the current application artifact.

## Canonical current candidate

The current product runtime remains Wave 76. The arm64 build is certified through the Wave 81 physical-UAT candidate guard. The canonical FULL MAC workflow now invokes `build_full_mac_current_guarded.sh` directly.

The resulting ZIP is named:

`Binario-Marketing-IA-PHYSICAL-UAT-arm64-<git-sha-12>.zip`

The GitHub Actions artifact is named:

`binario-marketing-physical-uat-candidate-arm64`

## External delivery metadata

Packaging is performed by `scripts/package_current_arm64_candidate.py`. The packager refuses to deliver a candidate unless the embedded Wave 81 manifest:

- is `binario.marketing.physical-uat-candidate.v1`;
- is marked `PHYSICAL_UAT_CANDIDATE_ONLY`;
- is arm64;
- declares runtime Wave 76;
- declares certification guard Wave 81;
- matches the full expected Git SHA;
- contains a valid candidate source SHA-256;
- remains release-disabled and not production-ready;
- still requires explicit physical UAT and cannot auto-pass it.

`FULL_MAC_DELIVERY.json` is emitted as `binario.marketing.full-mac-delivery.v2` and exposes:

- exact Git SHA;
- product version;
- architecture;
- runtime Wave 76;
- certification guard Wave 81;
- candidate source SHA-256;
- candidate manifest SHA-256;
- artifact filename and SHA-256;
- explicit physical-UAT-required / no-auto-pass / no-release-authority flags.

For operator inspection without opening the `.app`, the workflow also exports copies of:

- `PHYSICAL_UAT_CANDIDATE.json`;
- `PHYSICAL_UAT_CANDIDATE.md`.

## Historical boundary

Wave 47 feature names and the Wave 47 product-surface audit are intentionally retained where they describe the historical layer being tested. They are not the current runtime or artifact identity.

## Release boundary

Wave 83 does not:

- change runtime Wave 76;
- change `0.9.0.dev1`;
- set `RELEASE_READY=True`;
- create a release tag;
- claim Developer ID signing or notarization;
- fabricate physical UAT evidence;
- weaken the Wave 82 release-publication hard stop.

The canonical current arm64 artifact is a physical-UAT candidate only.
