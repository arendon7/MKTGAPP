# Wave 81 · Exact Physical UAT Candidate Handoff

Wave 81 turns the certified arm64 bundle into a self-identifying physical-UAT candidate without granting it release authority.

## Why this wave exists

The product runtime is W76 and the build/release chain is now certified on both arm64 and x86_64, but physical UAT remains intentionally arm64-only. Historical release-UAT tooling still allowed an x86_64 bundle through its architecture check and did not explicitly require a non-CI physical arm64 host. W81 closes those gaps and binds every future manual UAT record to the exact candidate.

## Candidate manifest

Every current arm64 guarded build embeds:

- `PHYSICAL_UAT_CANDIDATE.json`
- `PHYSICAL_UAT_CANDIDATE.md`

The manifest records:

- exact Git SHA;
- deterministic SHA-256 over bundled `src`, `web` and `apps` source;
- architecture `arm64`;
- product version;
- runtime Wave 76 / `service_wave76_app`;
- certification guard Wave 81;
- hashes for build provenance, embedded readiness and launch chain;
- explicit fail-closed release state;
- explicit rule that physical UAT is manual and required;
- explicit rule that the W75/W76 synthetic sandbox is not release evidence.

The bundle is re-signed after the manifest is embedded, then W81 verifies the manifest against the actual packaged source.

## UAT evidence hardening

`collect_release_uat.py` now requires all of the following before manual results can be recorded:

- physical host is Darwin arm64;
- CI is false;
- candidate bundle is arm64;
- W81 candidate manifest exists and matches provenance;
- candidate runtime is W76;
- codesign integrity passes;
- embedded engineering readiness exists.

Evidence now records both `candidate_source_sha256` and `candidate_manifest_sha256`.

`record_release_uat.py` refuses manual evidence unless those exact digests are present, the runtime is W76, the candidate is arm64, automatic checks passed and the human note contains a concrete observation.

`release_candidate_gate.py` rejects evidence whose candidate source or manifest digest differs from the evaluated arm64 `.app`.

## Boundaries preserved

- `0.9.0.dev1`
- `RELEASE_READY=False`
- `RELEASE_TAG=None`
- no release tag
- no notarization claim
- no automatic UAT PASS
- no synthetic sandbox release authority
- no provider, marketing, paid-media or AI mutation
- x86_64 remains distribution-certified but does not become eligible physical-UAT evidence

## Next gate

After W81 is green and merged, the exact arm64 artifact can be handed to a human operator for real physical UAT. Only evidence collected from that exact bundle on a non-CI arm64 Mac can remove the physical-UAT blocker; version, release flag/tag, Developer ID signing and notarization remain independent blockers.
