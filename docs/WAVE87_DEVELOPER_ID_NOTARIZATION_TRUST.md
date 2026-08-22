# Wave 87 · Developer ID + Notarization Distribution Trust

Wave 86 transports verified physical-UAT evidence into the tag workflow. Wave 87 adds the independent macOS distribution-trust gate required before an immutable asset can be packaged.

## Tag-only credential contract

The tag path requires real GitHub Actions secrets:

- `APPLE_DEVELOPER_ID_P12_BASE64`
- `APPLE_DEVELOPER_ID_P12_PASSWORD`
- `APPLE_DEVELOPER_IDENTITY`
- `APPLE_NOTARY_KEY_P8_BASE64`
- `APPLE_NOTARY_KEY_ID`
- `APPLE_NOTARY_ISSUER_ID`

Pull-request certification does not consume these secrets and remains ad-hoc signed.

## Distribution sequence

For each native architecture (`arm64`, `x86_64`) the tag workflow now:

1. creates an ephemeral keychain;
2. imports the Developer ID Application certificate;
3. verifies the expected signing identity exists;
4. builds the canonical Wave 76 app with that identity;
5. runs the normal bundle audit and service smoke;
6. submits the signed app to Apple `notarytool --wait`;
7. requires status `Accepted`;
8. staples and validates the notarization ticket;
9. requires Gatekeeper `spctl --assess` success;
10. re-verifies the final code signature;
11. emits `binario.marketing.distribution-trust.v1` evidence bound to Git SHA, architecture and product version;
12. verifies that evidence;
13. passes both W85 physical-UAT evidence and W87 distribution evidence into `release_candidate_gate.py --production`;
14. only then packages the immutable asset.

The publish job re-verifies both architecture-specific distribution-evidence files before creating any GitHub Release.

## Why notarization is external evidence

`BUILD_PROVENANCE.json` is embedded before final signing and therefore records the build-time signing mode but cannot be mutated after notarization without invalidating the code signature. W87 records notarization as external cryptographically checksummed evidence produced only after `notarytool`, stapler, Gatekeeper and final `codesign --verify` all succeed. The production gate accepts that evidence only when its SHA, architecture and version match the current bundle.

## Boundary preserved

W87 does not provide, generate or fabricate Apple credentials. It does not set repository secrets, create a tag, enable release flags, run physical UAT, or publish an asset. Current state remains:

- runtime Wave 76;
- version `0.9.0.dev1`;
- `RELEASE_READY=False`;
- `RELEASE_TAG=None`;
- exactly three workflows.

## Known pre-enable gate

The historical physical-candidate writer was intentionally designed for a fail-closed development candidate. Before release flags are ever changed, release-mode/tag-build semantics must be audited so the distribution rebuild does not incorrectly reuse a development-only physical-candidate assumption. This is a separate gate; W87 does not relax it.
