# Wave 86 · Safe Physical-UAT Evidence Transport

Wave 85 produces one sanitized combined attestation for the exact trusted physical arm64 candidate. Wave 86 transports that attestation into the existing tag-driven release workflow without committing evidence into the repository and therefore without changing the certified source SHA.

## Transport contract

The future release operator stores the exact contents of `combined-physical-uat-attestation.json`, base64 encoded, in the GitHub Actions secret `PHYSICAL_UAT_ATTESTATION_B64`.

On a version-tag push, `Persistent Mac Release` now:

1. verifies the canonical version/tag contract;
2. decodes the secret only inside `release-preflight`;
3. runs `verify_combined_uat_attestation.py` and requires the attested Git SHA to equal `GITHUB_SHA`;
4. uploads only that sanitized JSON as a short-lived verified Actions artifact;
5. both native build jobs download the same verified artifact;
6. each native build runs `release_candidate_gate.py --production --uat-evidence ...` before immutable packaging;
7. packaging and publication remain unreachable when any production blocker exists.

Raw Phase A or Phase B operator notes are not transported by this mechanism.

## Source-equivalent rebuild semantics

Physical UAT still happens only on the real non-CI arm64 candidate created from controlled `main` push.

A later tag build from the same commit has a different `build_origin.ref`, so its candidate manifest hash is expected to differ even when the packaged source is identical. W86 therefore permits a combined physical-UAT attestation to authorize a rebuild only when all of these remain identical:

- exact Git commit SHA;
- product version;
- runtime Wave 76;
- deterministic digest of packaged `src/`, `web/` and `apps/`.

The gate reports the distinction explicitly:

- `exact_physical_candidate`;
- `source_equivalent_arm64_rebuild`;
- `source_equivalent_cross_arch_distribution`.

For x86_64, this is source-equivalent distribution authorization backed by W80 native Intel certification. It is never represented as physical x86 UAT; the gate emits `x86_physical_uat_claimed=false`.

## Security / release boundary

W86 does **not**:

- set or change the Actions secret;
- create a release tag;
- set `RELEASE_READY=True`;
- set `RELEASE_TAG`;
- sign with Developer ID;
- notarize an application;
- publish a GitHub Release;
- make physical UAT automatic;
- accept PR, CI or synthetic sandbox execution as physical evidence.

Current product state remains `0.9.0.dev1`, `RELEASE_READY=False`, `RELEASE_TAG=None` and runtime Wave 76.

## Remaining release gates

After real W85 physical evidence exists and the sanitized attestation is placed in the Actions secret, the next release-engineering work is distribution trust: Developer ID signing, notarization and provenance verification for both native assets. Only after those gates are implemented and certified should the canonical version contract be considered for release enablement.
