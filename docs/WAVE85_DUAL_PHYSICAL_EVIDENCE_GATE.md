# Wave 85 · Dual Physical Evidence Gate

## Purpose

Wave 85 closes the release-evidence gap left intentionally open by W84. A physical product UAT PASS and a release operational UAT PASS are now separate required inputs; neither can satisfy the release UAT blocker by itself.

Runtime remains Wave 76. Candidate trust remains Wave 84. W85 is a certification/evidence guard only.

## Phase A export

`collect_product_uat.py` validates one completed `binario.marketing.physical-uat-session.v1` against the exact trusted W84 candidate. It requires:

- trusted `PHYSICAL_UAT_CANDIDATE_ONLY` origin;
- real physical-machine session eligibility;
- session `PASSED` and `physical_uat_complete=true`;
- all required product scenarios PASS;
- valid session evidence SHA-256;
- exact Git SHA, arm64 architecture and product version;
- exact candidate source SHA-256 and candidate manifest SHA-256.

It emits `binario.marketing.product-uat-evidence.v2` with `product_uat_passed=true`, but with no release authority.

The W85 handoff packages both `PRODUCT_UAT_COLLECT.py` and `COLLECT_PRODUCT_UAT.command` and binds their SHA-256 values in `FULL_MAC_DELIVERY.json`.

## Dual release gate

`release_candidate_gate.py` now accepts:

- `--product-uat-evidence` for Phase A;
- `--uat-evidence` for Phase B.

The canonical readiness evaluator receives `uat_passed=true` only when both phases pass. Both evidence files must match the same:

- Git SHA;
- candidate source SHA-256;
- candidate manifest SHA-256;
- arm64/W76 candidate contract.

Explicit blockers distinguish missing/invalid Phase A, missing/invalid Phase B, and cross-phase binding mismatch.

## Boundaries

W85 does not change `0.9.0.dev1`, runtime W76, `RELEASE_READY=False`, `RELEASE_TAG=None`, signing mode, notarization or publication behavior. W82 still prevents release publication. No CI or synthetic evidence can become physical evidence.

## Next step after merge

Use only the trusted post-merge main candidate, complete Phase A and Phase B on that exact candidate, export both evidence files, and run the dual release gate. Developer ID signing, notarization, production versioning and tag publication remain later independent gates.
