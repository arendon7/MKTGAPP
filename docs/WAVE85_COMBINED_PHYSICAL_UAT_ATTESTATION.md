# Wave 85 · Combined Physical UAT Attestation

Wave 84 makes the exact trusted arm64 candidate operable for two independent evidence layers. Wave 85 combines those layers into one sanitized, cryptographically bound attestation without granting release authority or inventing an unsafe evidence-transport channel.

## Evidence layers

### Phase A · In-app physical product UAT

The app-generated `binario.marketing.physical-uat-evidence.v1` report must prove, for the exact candidate:

- session `PASSED`;
- `physical_uat_complete=true`;
- real Darwin arm64 non-CI machine eligibility;
- every required scenario is `PASS`;
- session evidence digest is valid;
- session build SHA, architecture and product version match the candidate exactly.

### Phase B · Release operational UAT

The handoff-generated `binario.marketing.release-uat-evidence.v1` report must prove:

- automatic candidate checks passed;
- all 12 manual release gates are `PASS`;
- every manual gate has a concrete note and recorded timestamp;
- `uat_passed=true` and `overall=UAT_PASS`;
- candidate SHA, architecture, runtime wave, source digest and manifest digest match exactly.

## Combined attestation

`scripts/finalize_physical_uat.py` accepts the trusted arm64 `.app`, one Phase A report and one Phase B report. It emits `combined-physical-uat-attestation.json` and a Markdown summary.

The JSON contains only release-relevant metadata and hashes. It deliberately excludes operator notes and other raw UAT narrative so it can later be transported without unnecessarily exposing local test details.

The combined attestation is valid only when both phases pass on the same exact trusted candidate. It records Git SHA, product version, arm64 architecture, runtime Wave 76, candidate digests, Phase A/Phase B report hashes and a deterministic attestation digest. It always records `release_authority=false`.

## Release boundary

Wave 85 does **not** set `RELEASE_READY=True`, set a release tag, create a GitHub Release, sign with Developer ID, notarize the app, accept CI/sandbox evidence, or execute marketing/provider actions.

The persistent release workflow remains fail-closed until a later wave implements reviewed durable transport of this combined attestation to the exact tag target without weakening exact-build provenance.

## Why transport remains separate

Committing the attestation into the UAT-tested commit would change its Git SHA and invalidate exact-build evidence. Wave 85 therefore produces the transport-safe artifact but does not pretend that committing it into source is a correct solution.
