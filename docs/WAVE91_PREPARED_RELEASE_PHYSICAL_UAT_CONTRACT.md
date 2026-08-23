# Wave 91 · Prepared Release Physical UAT Contract

## Purpose

Wave 91 closes a release-integrity paradox that existed across the otherwise fail-closed W81–W90 chain.

Before W91, an exact physical-UAT candidate was allowed only when the canonical source declared:

- `RELEASE_READY=False`
- `RELEASE_TAG=None`

but the tag verifier allowed a release only when that same source declared:

- `RELEASE_READY=True`
- `RELEASE_TAG=v<version>`

Changing those fields after physical UAT changes the commit SHA and the `src/web/apps` source digest. W85/W86 intentionally bind physical evidence to those exact values, so a post-UAT source mutation would make the tested commit different from the released commit.

W91 removes that contradiction without enabling release today.

## Source release contract

`src/binario_marketing/release_contract.py` defines two source-level states.

### `LOCKED_SOURCE`

The ordinary development state:

- `RELEASE_READY=False`
- `RELEASE_TAG=None`
- development versions are allowed
- physical UAT may still be performed for engineering certification
- no operational release authority exists

### `PREPARED_RELEASE`

A future, intentionally prepared source commit:

- version must be stable, not `.dev`, `alpha`, `beta` or `rc`
- `RELEASE_READY=True`
- `RELEASE_TAG` must be exactly `v<version>`
- the contract must exist **before** physical UAT
- the exact commit physically tested on `main` is the commit that must later receive the tag

`PREPARED_RELEASE` is source intent, not publication authority. It never implies Developer ID signing, notarization, operational authorization, production readiness or a GitHub Release.

## Exact physical candidate identity

Wave 91 reinforces the W88 separation:

- exact physical UAT candidate: controlled GitHub `push` to `refs/heads/main`, arm64 only;
- tag build: source-equivalent distribution rebuild, never an exact physical candidate;
- PR/local/workflow-dispatch build: validation-only.

A future prepared source commit is therefore merged to `main`, the `main` arm64 artifact is physically tested, and only after its evidence passes may `v<version>` point to that same SHA.

## Physical preflight semantics

The in-app W69 preflight retains the historical check id `release-fail-closed`, but W91 gives that check the correct semantic meaning:

- source contract is valid (`LOCKED_SOURCE` or `PREPARED_RELEASE`);
- candidate contract matches bundled source;
- bundle is still `release_channel=development`;
- signing remains ad-hoc;
- bundle is not notarized;
- `production_ready=false`;
- `release_authority=false`.

This allows physical UAT of a prepared source commit while still proving the physical test bundle is not a distributable production artifact.

## Evidence chain

### Candidate and handoff

`PHYSICAL_UAT_CANDIDATE.json` and `FULL_MAC_DELIVERY.json` now bind the source release contract alongside:

- exact Git SHA;
- `candidate_source_sha256`;
- candidate manifest digest;
- arm64 architecture;
- runtime Wave 76;
- physical origin;
- no automatic UAT pass;
- no production authority.

### Phase B operational UAT

`release-uat-evidence.json` records the source release contract used by the exact candidate. All 12 manual release-operational gates remain required.

### Combined W85 attestation

The combined attestation now binds the release contract and emits both guard names:

- historical `candidate_guard_wave=84`;
- canonical `certification_guard_wave=84`.

They must agree. This repairs the historical W85/W86 field-name mismatch without invalidating legacy W85 evidence verification.

### W86/W91 transport verification

`verify_combined_uat_attestation.py` validates the guard aliases and optional release-contract binding.

`verify_prepared_release_uat.py` is stricter and is required for an actual tag path. It requires:

1. canonical source is `PREPARED_RELEASE`;
2. workflow tag equals canonical `RELEASE_TAG` and `v<version>`;
3. combined UAT SHA equals tag checkout SHA;
4. physical UAT release contract equals current source release contract;
5. combined evidence carries the W91 contract layer;
6. freshly recomputed `src/web/apps` digest equals the digest physically tested.

Legacy or `LOCKED_SOURCE` evidence cannot authorize a prepared tag.

## Persistent release workflow

Wave 91 preserves exactly the three canonical workflow files.

The tag path now orders the relevant gates as:

1. canonical tag verification;
2. decode + combined physical-UAT verification;
3. W91 same-commit prepared-release UAT verification;
4. upload verified evidence;
5. native jobs download evidence;
6. native jobs repeat W91 verification on their own checkout;
7. Developer ID credential gate;
8. source-equivalent distribution rebuild;
9. runtime smoke;
10. Apple notarization + distribution trust verification;
11. production `release_candidate_gate.py`;
12. immutable packaging;
13. cross-architecture publication verification;
14. `gh release create`.

The W91 verification report is preserved with each architecture's release artifacts.

## Stable-version PR readiness

The Intel PR certification no longer hardcodes `0.9.0.dev1`. It compares `BUILD_PROVENANCE.json.product_version` with the canonical `version.py` in the same checkout. This is necessary so a future stable-version preparation PR can be certified rather than being rejected merely because the version changed intentionally.

## Current repository boundary

Wave 91 does **not** prepare or publish a release.

The canonical source remains:

- `__version__ = "0.9.0.dev1"`
- `RELEASE_READY = False`
- `RELEASE_TAG = None`
- runtime Wave 76

Therefore `release_enablement_audit.py` remains `BLOCKED` today.

No tag is created. No Developer ID credential is fabricated. No notarization is claimed. No physical UAT is fabricated. No GitHub Release is published.

## Future correct release sequence

When product owners intentionally decide to prepare a real release:

1. make one reviewed source commit that changes the version to a stable value and declares its exact `RELEASE_TAG`;
2. certify that PR on Source CI, arm64 and Intel;
3. merge that prepared commit to `main`;
4. use the exact `main` arm64 candidate for physical Phase A + Phase B UAT;
5. generate the combined attestation;
6. verify all evidence against the prepared commit;
7. create the canonical tag pointing to **that same commit**, with no source changes;
8. let the tag workflow rebuild source-equivalent Developer ID distributions, notarize them and run production gates;
9. publish only if every runtime gate succeeds.

That sequence preserves the central invariant introduced by W91:

> The source commit physically tested is the source commit tagged for release.
