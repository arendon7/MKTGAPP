#!/usr/bin/env bash
set -euo pipefail

READINESS=src/binario_marketing/release_readiness.py
CANDIDATE=scripts/write_physical_uat_candidate.py
COLLECTOR=scripts/collect_release_uat.py
RECORDER=scripts/record_release_uat.py
FINALIZER=scripts/finalize_physical_uat.py
COMBINED=scripts/verify_combined_uat_attestation.py
HANDOFF=scripts/verify_physical_uat_handoff.py
DISTRIBUTION=scripts/write_distribution_rebuild_manifest.py
GATE=scripts/release_candidate_gate.py
TAG=scripts/verify_release_tag.py
WORKFLOW=.github/workflows/persistent-release.yml
AUDIT=scripts/release_enablement_audit.py
VERSION=src/binario_marketing/version.py

for path in "$READINESS" "$CANDIDATE" "$COLLECTOR" "$RECORDER" "$FINALIZER" "$COMBINED" "$HANDOFF" "$DISTRIBUTION" "$GATE" "$TAG" "$WORKFLOW" "$AUDIT" "$VERSION"; do
  test -f "$path"
done

grep -q 'LOCKED_SOURCE' "$READINESS"
grep -q 'PREPARED_RELEASE' "$READINESS"
grep -q 'source_release_state' "$READINESS"

grep -q 'SOURCE_CONTRACT_WAVE = 95' "$CANDIDATE"
grep -q 'refs/heads/main' "$CANDIDATE"
grep -q 'prepared_release_required_for_future_production' "$CANDIDATE"

for path in "$COLLECTOR" "$RECORDER" "$FINALIZER" "$HANDOFF"; do
  grep -q '95' "$path"
  grep -q 'source_release_state' "$path"
  grep -q 'source_release_tag' "$path"
done

grep -q 'EXPECTED_SOURCE_CONTRACT_WAVE = 95' "$COMBINED"
grep -q 'expected_source_release_state' "$COMBINED"
grep -q 'expected_release_tag' "$COMBINED"

grep -q 'SOURCE_CONTRACT_WAVE = 95' "$DISTRIBUTION"
grep -q 'tag distribution rebuild requires PREPARED_RELEASE' "$DISTRIBUTION"
grep -q 'distribution rebuild tag/source contract mismatch' "$DISTRIBUTION"

grep -q 'EXPECTED_SOURCE_CONTRACT_WAVE = 95' "$GATE"
grep -q 'prepared_release_uat_required' "$GATE"
grep -q 'prepared_release_tag_mismatch' "$GATE"
grep -q 'prepared_release_source_required' "$GATE"

grep -q 'release tag requires PREPARED_RELEASE' "$TAG"
grep -q -- '--expected-source-release-state PREPARED_RELEASE' "$WORKFLOW"
grep -q -- '--expected-release-tag "$GITHUB_REF_NAME"' "$WORKFLOW"
grep -q 'from binario_marketing.version import __version__' "$WORKFLOW"
! grep -q "row\['product_version'\]=='0.9.0.dev1'" "$WORKFLOW"

grep -q 'release-enablement-audit.v7' "$AUDIT"
grep -q 'certification_guard_wave": 95' "$AUDIT"
grep -q 'w95_preserves_w94_before_w93' "$AUDIT"

# W95 defines the two-state source contract. Later waves may move the canonical
# source from LOCKED_SOURCE to PREPARED_RELEASE, but must stay coherent and
# non-authoritative until external operational evidence exists.
PYTHONPATH=src python - <<'PY'
from binario_marketing.release_readiness import LOCKED_SOURCE, PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__

state = source_release_state()
assert state in {LOCKED_SOURCE, PREPARED_RELEASE}
report = source_release_readiness()
assert report["production_ready"] is False
if state == LOCKED_SOURCE:
    assert RELEASE_READY is False
    assert RELEASE_TAG is None
else:
    assert RELEASE_READY is True
    assert RELEASE_TAG == f"v{__version__}"
    assert report["source_ready"] is True
    assert report["stage"] == "SOURCE_CONTRACT_READY"
    assert report["operational_inputs_complete"] is False
PY

# Canonical workflow count remains exactly three.
test "$(find .github/workflows -maxdepth 1 -type f -name '*.yml' | wc -l | tr -d ' ')" = "3"

echo 'WAVE 95 PREPARED RELEASE SHA STABILITY AUDIT PASS'
