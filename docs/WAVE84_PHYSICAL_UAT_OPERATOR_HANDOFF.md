# Wave 84 · Physical UAT Operator Handoff

## Purpose

Wave 84 turns the exact W83 arm64 candidate into an operator-ready physical-UAT handoff without granting release authority or fabricating evidence.

The candidate remains runtime Wave 76 with the Wave 81 exact-candidate guard. Wave 84 is an operator handoff layer only.

## Why two UAT phases exist

The certified product already contains two distinct evidence contracts and they must not be conflated:

### Phase A · In-app physical product UAT

Wave 67–70 stores manual product-journey evidence on the real Mac. Five scenarios are required:

- `company-switch`
- `inbox-to-crm`
- `pipeline-followup`
- `campaign-execution`
- `results-decision`

`optional-ai` is optional.

A session is physically complete only when all required scenarios PASS on a real non-CI Darwin arm64 host. Wave 70 additionally requires the session evidence digest and exact build SHA/architecture/version to match the current bundle before it is accepted for that build.

### Phase B · Release operational UAT

`collect_release_uat.py` and `record_release_uat.py` maintain the separate `binario.marketing.release-uat-evidence.v1` contract used by the release candidate gate. It contains 12 manual operational gates covering launcher/relaunch, persistence, CRM, Today actions, content, social read-only behavior, manual reply, editorial management, video render, transcription and Keychain credentials.

Every gate requires an explicit PASS/FAIL plus a concrete note. The evidence remains bound to the exact Git SHA, candidate source SHA-256, candidate manifest SHA-256, arm64 architecture and runtime Wave 76.

## Operator package

The canonical arm64 Actions artifact now includes:

- `Binario-Marketing-IA-PHYSICAL-UAT-arm64-<sha12>.zip`
- ZIP `.sha256`
- `FULL_MAC_DELIVERY.json`
- `PHYSICAL_UAT_CANDIDATE.json`
- `PHYSICAL_UAT_CANDIDATE.md`
- `PHYSICAL_UAT_HANDOFF_VERIFY.py`
- `START_PHYSICAL_UAT.command`
- `RECORD_RELEASE_UAT.command`
- `PHYSICAL_UAT_OPERATOR.md`

`FULL_MAC_DELIVERY.json` binds the four operator helper files by SHA-256 and declares both UAT phases required.

## START_PHYSICAL_UAT.command

The starter fails closed unless it runs on a real Apple Silicon arm64 Mac outside CI. It then:

1. requires exactly one canonical PHYSICAL-UAT ZIP;
2. verifies the ZIP checksum;
3. extracts the exact candidate into `PHYSICAL_UAT_WORK`;
4. verifies codesign integrity;
5. runs the Wave 84 handoff verifier using the embedded Python runtime;
6. initializes release-UAT evidence if none exists;
7. preserves existing evidence only when it is bound to the same exact candidate;
8. opens the app;
9. prints the Phase A and Phase B operator sequence.

It does not mark any manual step PASS.

## RECORD_RELEASE_UAT.command

The recorder:

- requires the same real arm64 non-CI physical host;
- re-verifies the exact handoff before accepting evidence;
- lists all 12 manual release gates and their current statuses;
- accepts exactly one gate result at a time;
- requires PASS or FAIL plus a non-empty concrete observation;
- delegates durable mutation to the existing hardened `record_release_uat.py` contract;
- reports remaining pending/failed gates.

## Safety boundary

Wave 84 does not:

- change runtime Wave 76;
- change `0.9.0.dev1`;
- set `RELEASE_READY=True`;
- create a release tag;
- claim Developer ID signing or notarization;
- execute physical UAT in CI;
- turn synthetic W75/W76 sandbox evidence into physical evidence;
- infer Phase A from Phase B or Phase B from Phase A;
- publish marketing or activate paid media.

The Wave 82 release publication hard stop remains intact.

## Remaining release gap

Wave 84 makes both evidence layers explicit and operable. A later release-gate wave must still require both layers structurally before the persistent tag workflow can satisfy the Wave 82 production contract. Until then, release publishing remains intentionally blocked.
