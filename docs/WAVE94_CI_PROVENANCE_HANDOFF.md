# Wave 94 · CI Provenance Handoff

Wave 93 makes GitHub Release publication transactional. Wave 94 adds a cryptographic identity boundary before that transaction: each exact native release ZIP must be attributable to the canonical GitHub Actions workflow, repository, release tag and source commit through GitHub OIDC/Sigstore provenance.

## Contract

1. W92 still proves each packaged ZIP survives extraction with Developer ID, notarization and Gatekeeper trust intact.
2. `actions/attest@v4.2.1` attests the exact ZIP path emitted by the package step for `arm64` and `x86_64`.
3. Each Sigstore bundle is persisted as `CI-PROVENANCE-<arch>.sigstore.json` with the native release artifact.
4. Final verification uses the exact repository, signer workflow, tag ref, git SHA, GitHub OIDC issuer and SLSA v1 predicate, while denying self-hosted runner attestations.
5. `RELEASE-CI-PROVENANCE-AUTHORIZATION.json` requires both native ZIP digests to match W92 and binds the SHA-256 of `scripts/publish_release_transaction.sh`.
6. W94 grants only `transaction_handoff_authority`; it deliberately keeps `publication_authority=false`.
7. W93 verifies the W94 seal/tag/SHA/publisher digest before its first GitHub Release operation and remains the only publication mutation boundary.

## Least privilege

- workflow default: `contents: read`;
- `build-native`: `contents: read`, `id-token: write`, `attestations: write`, `artifact-metadata: write`;
- `publish-release`: `contents: write` only where publication is required;
- PR runs keep `release-preflight`, `build-native` and `publish-release` skipped.

## Fail-closed cases

W94 blocks wrong repository, signer workflow, source ref, source commit, SLSA predicate, OIDC issuer, self-hosted provenance, absent timestamp/transparency witness, wrong asset filename/SHA-256, cross-architecture drift, W92 reuse for another tag/commit, authorization tamper, or any change to the transaction script after authorization.

## Boundary

Runtime remains Wave 76. Current source remains `0.9.0.dev1`, `RELEASE_READY=False`, `RELEASE_TAG=None`. W94 creates no tag, no release and no external evidence in PR CI. Physical UAT and real tag-runtime Apple/OIDC evidence remain external facts that source auditing must never infer.
