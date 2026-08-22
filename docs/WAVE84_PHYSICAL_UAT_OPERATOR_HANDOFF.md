# Wave 84 · Trusted Physical UAT Operator Handoff

## Purpose

Wave 84 turns the exact W83 arm64 delivery into an operator-ready physical-UAT handoff while making one distinction explicit: a pull-request validation build is not physical-UAT evidence.

The product runtime remains Wave 76. Wave 84 is a certification/operator layer; it does not grant release authority.

## Trusted build-origin contract

`PHYSICAL_UAT_CANDIDATE.json` records `build_origin` and derives its role from the real GitHub event/ref:

- controlled `push` to `refs/heads/main` or `refs/tags/v*` → `PHYSICAL_UAT_CANDIDATE_ONLY`, `eligible_build_origin=true`;
- pull request, workflow dispatch, local build or any other origin → `VALIDATION_BUILD_ONLY`, `eligible_build_origin=false`.

The trust bit is re-derived during verification. It is not a user-controlled override. A PR artifact may be fully built, audited and smoke-tested, but `START_PHYSICAL_UAT.command` must reject it even on a real arm64 Mac.

## Two physical evidence phases

### Phase A · In-app product UAT

Five scenarios are required: `company-switch`, `inbox-to-crm`, `pipeline-followup`, `campaign-execution`, `results-decision`. `optional-ai` remains optional.

The W69 preflight now requires the trusted build-origin contract in addition to physical arm64 host, embedded runtime, version and fail-closed release state. Start/update/finish UAT mutations are server-side preflight-gated, so a validation artifact cannot create physical evidence.

### Phase B · Release operational UAT

`collect_release_uat.py` / `record_release_uat.py` retain the 12 explicit manual release gates. Collection additionally requires `PHYSICAL_UAT_CANDIDATE_ONLY`, trusted GitHub origin, arm64, real non-CI host, W76 runtime, W84 manifest, codesign and exact SHA/source/manifest binding.

## Operator package

The Actions handoff includes the exact candidate ZIP/checksum, `FULL_MAC_DELIVERY.json`, external candidate manifest/summary, verifier, start command, record command and operator guide. Helper files are SHA-256 bound.

For workflow compatibility the external ZIP name remains `Binario-Marketing-IA-PHYSICAL-UAT-arm64-<sha12>.zip`; the authoritative eligibility fields are the manifest/delivery `role`, `build_origin` and `physical_uat_eligible`.

## START_PHYSICAL_UAT.command

The starter requires a real non-CI Apple Silicon Mac and then verifies checksum, extraction, codesign and the W84 handoff. The verifier additionally requires trusted physical role/origin before evidence is initialized or the app opens. Therefore a PR-delivered handoff is inspectable but intentionally unusable for physical UAT.

## Safety boundary

Wave 84 does not change runtime W76, `0.9.0.dev1`, `RELEASE_READY=False` or `RELEASE_TAG=None`; does not auto-pass UAT; does not turn sandbox evidence into physical evidence; does not claim Developer ID/notarization; and does not publish marketing or activate paid media.

The W82 release-publication hard stop remains intact and W83 exact artifact identity remains intact.

## Next gate

After W84 is green and merged, only the post-merge `push main` arm64 artifact whose delivery reports `PHYSICAL_UAT_CANDIDATE_ONLY` and `physical_uat_eligible=true` may be handed to the operator. Complete Phase A and Phase B on that exact build. Developer ID signing, notarization and production version/tag remain independent later gates.
