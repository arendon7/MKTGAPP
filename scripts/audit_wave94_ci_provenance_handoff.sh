#!/usr/bin/env bash
set -euo pipefail

WORKFLOW=.github/workflows/persistent-release.yml
PROVENANCE=scripts/release_ci_provenance_authorization.py
TRANSACTION=scripts/publish_release_transaction.sh
VERSION=src/binario_marketing/version.py

test -f "$WORKFLOW"
test -f "$PROVENANCE"
test -f "$TRANSACTION"
test -f "$VERSION"

grep -q 'uses: actions/attest@v4.2.1' "$WORKFLOW"
grep -q 'id-token: write' "$WORKFLOW"
grep -q 'attestations: write' "$WORKFLOW"
grep -q 'artifact-metadata: write' "$WORKFLOW"
grep -q 'subject-path: \${{ steps.package.outputs.zip_path }}' "$WORKFLOW"
grep -q 'CI-PROVENANCE-\${{ matrix.arch }}.sigstore.json' "$WORKFLOW"
grep -q 'Build W94 CI provenance transaction handoff' "$WORKFLOW"
grep -q 'Verify W94 CI provenance transaction handoff' "$WORKFLOW"
grep -q -- '--transaction-script scripts/publish_release_transaction.sh' "$WORKFLOW"
grep -q 'binario.marketing.release-ci-provenance-authorization.v2' "$PROVENANCE"
grep -q 'CERTIFICATION_GUARD_WAVE = 94' "$PROVENANCE"
grep -q -- '--deny-self-hosted-runners' "$PROVENANCE"
grep -q 'https://slsa.dev/provenance/v1' "$PROVENANCE"
grep -q 'https://token.actions.githubusercontent.com' "$PROVENANCE"
grep -q 'transaction_handoff_authority' "$PROVENANCE"
grep -q 'W94_STAGE_PROVENANCE_HANDOFF' "$TRANSACTION"
grep -q 'verify-transaction-handoff' "$TRANSACTION"
grep -q 'RELEASE-CI-PROVENANCE-AUTHORIZATION.json' "$TRANSACTION"
grep -q '__version__ = "0.9.0"' "$VERSION"
grep -q 'RELEASE_READY = True' "$VERSION"
grep -q 'RELEASE_TAG: str | None = "v0.9.0"' "$VERSION"

python - "$WORKFLOW" "$TRANSACTION" <<'PY'
from pathlib import Path
import sys
workflow=Path(sys.argv[1]).read_text(encoding='utf-8')
transaction=Path(sys.argv[2]).read_text(encoding='utf-8')
w92=workflow.index('Verify W92 final publication authorization')
w94_build=workflow.index('Build W94 CI provenance transaction handoff')
w94_verify=workflow.index('Verify W94 CI provenance transaction handoff')
publisher=workflow.index('bash scripts/publish_release_transaction.sh')
assert w92 < w94_build < w94_verify < publisher, (w92,w94_build,w94_verify,publisher)
handoff=transaction.index('W94_STAGE_PROVENANCE_HANDOFF')
preexisting=transaction.index('W93_STAGE_PREEXISTING_RELEASE_CHECK')
draft=transaction.index('W93_STAGE_DRAFT_CREATE')
assert handoff < preexisting < draft, (handoff,preexisting,draft)
print('WAVE 94 CI PROVENANCE HANDOFF ORDER PASS')
PY

echo 'WAVE 94 CI PROVENANCE HANDOFF AUDIT PASS'
