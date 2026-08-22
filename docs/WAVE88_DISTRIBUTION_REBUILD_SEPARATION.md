# Wave 88 · Distribution Rebuild Separation

## Objective

Separate two identities that must never be conflated:

1. **Exact physical-UAT candidate** — the exact arm64 bundle produced by a trusted `push` to `refs/heads/main` and eligible for real non-CI physical UAT.
2. **Source-equivalent distribution rebuild** — a tag-triggered arm64 or x86_64 rebuild authorized only through exact source equivalence to the physically attested commit.

Wave 88 changes no product runtime. The canonical runtime remains Wave 76.

## Exact physical candidate boundary

`PHYSICAL_UAT_CANDIDATE.json` is now trusted only when the build origin is:

- event: `push`
- ref: `refs/heads/main`
- architecture: `arm64`

A `refs/tags/v*` build is explicitly **not** a physical-UAT candidate. Pull requests, local builds and workflow dispatches remain validation-only.

## Distribution rebuild identity

Tag builds run `build_full_mac_release_candidate.sh --distribution` and produce:

- `Contents/Resources/DISTRIBUTION_REBUILD.json`
- schema: `binario.marketing.distribution-rebuild.v1`
- purpose: `SOURCE_EQUIVALENT_DISTRIBUTION_REBUILD`
- exact git SHA
- architecture
- product version
- runtime Wave 76
- deterministic `src/web/apps` source SHA-256
- tag-push build origin
- explicit `physical_uat.claimed=false`
- explicit `physical_uat.exact_bundle_tested=false`
- authorization mode `source_equivalent_only`
- `release_authority=false`

A distribution rebuild is rejected if either physical-candidate file is present.

## Distribution signing

Distribution mode requires a real `Developer ID Application:` identity and performs the final bundle signature with:

- hardened runtime (`--options runtime`)
- secure timestamp (`--timestamp`)

That final signed bundle then proceeds through the Wave 87 notarization, stapling, Gatekeeper and distribution-trust evidence pipeline.

## Production gate

For production, `release_candidate_gate.py` now requires all of the following:

- valid W85 combined physical-UAT attestation;
- source-equivalent UAT binding for the current distribution architecture;
- valid `DISTRIBUTION_REBUILD.json` matching the current SHA, architecture, version, runtime and source digest;
- valid Wave 87 Developer ID/notarization/Gatekeeper evidence;
- canonical release/version readiness gates.

A bundle containing both physical-candidate and distribution-rebuild identities is blocked.

## Release boundary preserved

Wave 88 does **not**:

- change runtime Wave 76;
- change `0.9.0.dev1`;
- set `RELEASE_READY=True`;
- set `RELEASE_TAG`;
- create a tag;
- create a GitHub Release;
- fabricate physical UAT;
- populate Apple or UAT secrets;
- add a fourth workflow.

The release remains fail-closed until real physical evidence and the remaining explicit release-enablement decisions exist.
