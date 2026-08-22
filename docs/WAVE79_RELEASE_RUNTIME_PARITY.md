# Wave 79 · Persistent Release Runtime Parity

Wave 79 closes a release-pipeline correctness gap discovered after W78.

## Defect corrected

The iteration workflow already reconstructed the current W76 runtime and applied the W78 certification guard, but `Persistent Mac Release` still called the historical base builder directly. That base builder creates a launch chain ending at W45. A future release could therefore have been built from an older runtime if release publishing were enabled without first correcting the builder path.

## W79 contract

- Persistent release must never call `build_full_mac_app.sh` directly.
- Release candidates must enter through `build_full_mac_release_candidate.sh`.
- The arm64 candidate delegates to the already-certified current builder and must contain `service_wave76_app import serve`.
- x86_64 is explicitly fail-closed until the current W76 + W78 chain is separately certified for Intel; it must never fall back to the W45 base runtime.
- Publishing still requires both architectures, so no permanent release can be created while x86_64 current-runtime parity remains uncertified.
- Release manifests identify `runtime_wave=76` and `certification_guard_wave=78`.
- `0.9.0.dev1`, `RELEASE_READY=False`, and `RELEASE_TAG=None` remain unchanged.

## Safety boundary

W79 does not enable releases, create a version tag, notarize a bundle, record physical-UAT evidence, call providers, publish marketing content, activate paid media or perform AI generation.

## Next gate

1. Keep arm64 Source CI and FULL MAC green with W79 parity audit.
2. Certify the current runtime chain on x86_64 before any production release can satisfy the two-architecture policy.
3. Independently complete W76 sandbox journey and guided physical UAT on the exact eligible arm64 build before changing release readiness.
