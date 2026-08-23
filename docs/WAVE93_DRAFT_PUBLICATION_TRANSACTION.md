# Wave 93 · Draft Publication Transaction

W92 proves the exact packaged ZIP bytes and native trust before publication. W93 closes the final GitHub-hosting boundary: a release is never made public until GitHub has stored the authorized asset bytes and those bytes have been downloaded back and verified.

## Contract

1. Create the GitHub Release as a draft only.
2. Upload the already-authorized `release/*` payload.
3. Download the draft assets from GitHub.
4. Compare exact inventory, byte length and SHA-256 against the local authorized payload.
5. Emit `GITHUB-RELEASE-ROUNDTRIP.json`.
6. Upload that round-trip evidence to the draft.
7. Re-run the byte comparison before publication.
8. Publish by clearing the draft flag only after every prior step passes.
9. If the transaction fails while a draft exists, delete that draft. Never delete a non-draft release.

## Boundary

- Runtime remains Wave 76.
- W91 evidence-chain and W92 packaged-artifact authorization remain authoritative prerequisites.
- Product remains `0.9.0.dev1` with `RELEASE_READY=False` and `RELEASE_TAG=None` on current source.
- PR CI never creates a tag or release and never consumes Apple release credentials.
- W93 does not claim physical UAT, signing, notarization or production readiness from source/CI.
