# Wave 83 · Trusted Physical UAT Origin

Wave 81 binds physical UAT evidence to the exact arm64 W76 candidate. Wave 82 keeps tag-driven publication fail-closed until production UAT evidence is transported into the persistent release workflow. Wave 83 closes the remaining operational ambiguity: not every arm64 build is allowed to become physical-UAT evidence.

## Risk closed

Pull-request, local and workflow-dispatch builds can contain the same source tree as a later `main` build while carrying a different Git SHA/provenance identity. Running physical UAT on those validation artifacts would waste manual certification and could create evidence that cannot satisfy the final candidate.

## W83 contract

`PHYSICAL_UAT_CANDIDATE.json` now records a build origin and one of two roles:

- `PHYSICAL_UAT_CANDIDATE_ONLY`: controlled GitHub Actions `push` to `refs/heads/main` or a version tag `refs/tags/v*`;
- `VALIDATION_BUILD_ONLY`: pull request, local build, workflow dispatch or any other origin.

The role is derived from `GITHUB_EVENT_NAME` and `GITHUB_REF`; it is not supplied by a mutable user flag. Verification re-derives trust from the recorded origin and rejects a tampered trust bit.

Physical-UAT collection, the release-candidate gate and the in-app W69 preflight all require the same trusted-origin contract in addition to W81 SHA/source/manifest binding.

The in-app start/update/finish UAT mutations are preflight-gated, so a PR artifact cannot even begin recording physical UAT.

## Preserved boundaries

- product runtime remains Wave 76;
- certification guard becomes Wave 83;
- W82 release-publication hard stop remains intact;
- x86_64 remains distribution-certified but is not physical-UAT eligible;
- `0.9.0.dev1`;
- `RELEASE_READY=False`;
- `RELEASE_TAG=None`;
- no automatic UAT PASS;
- sandbox is not release evidence;
- no provider, publication, paid-media or AI mutation;
- exactly three canonical workflows.

## Certification behavior

On a pull request, FULL MAC must pass while producing `VALIDATION_BUILD_ONLY`.

After merge, the `push` run on `main` must pass while producing `PHYSICAL_UAT_CANDIDATE_ONLY`. That post-merge arm64 artifact is the correct handoff for real physical UAT.

## Next gate

After W83 is green and merged, identify the exact post-merge `main` arm64 artifact, verify its W83 manifest/provenance, run the W76 controlled sandbox to 6/6 on the physical Mac, and then execute the guided physical UAT. Release flags, Developer ID signing and notarization remain independent later gates.
