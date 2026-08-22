# Wave 82 · Release Publication Hard Stop

Wave 81 makes physical UAT evidence exact-candidate-bound. Wave 82 prevents the tag-driven release workflow from becoming publishable merely by changing the canonical version flags.

## Risk closed

`Persistent Mac Release` currently verifies `RELEASE_READY` and `RELEASE_TAG` before building, but it does not yet transport physical-UAT evidence into `release_candidate_gate.py --production`. Without an additional structural gate, a future version change could make tag preflight pass before the production evidence path is actually implemented.

## W82 contract

`verify_release_tag.py` now refuses a release tag unless the canonical persistent-release workflow contains, before immutable packaging:

- `release_candidate_gate.py`;
- `--production`;
- `--uat-evidence`;
- no `--expect-blocked` substitution;
- no `|| true` non-blocking escape.

The current workflow intentionally does not satisfy that contract yet. Therefore release publishing remains blocked even if someone were to change only `RELEASE_READY` and `RELEASE_TAG`.

## Why the workflow is not modified yet

Physical UAT evidence must come from the exact non-CI arm64 candidate established by W81/W82. The safe transport of that evidence into a later tag build is a separate release-engineering problem. W82 deliberately refuses to invent or simulate that evidence transport.

## Boundaries preserved

- runtime remains W76;
- `0.9.0.dev1`;
- `RELEASE_READY=False`;
- `RELEASE_TAG=None`;
- exactly three canonical workflows;
- no tag or GitHub Release is created;
- no notarization or Developer ID claim;
- no automatic UAT PASS;
- no provider, marketing, paid-media or AI mutation.

## Next release-engineering gate

After exact physical UAT evidence exists for a final trusted arm64 candidate, implement durable evidence transport into the existing persistent-release workflow, then make both architectures run `release_candidate_gate.py --production` before packaging. Developer ID signing and notarization remain independent requirements.
