#!/usr/bin/env bash
set -euo pipefail

WORKFLOW=.github/workflows/persistent-release.yml
TRANSACTION=scripts/publish_release_transaction.sh
VERIFIER=scripts/verify_published_release_roundtrip.py

test -f "$WORKFLOW"
test -f "$TRANSACTION"
test -f "$VERIFIER"

grep -q 'bash scripts/publish_release_transaction.sh' "$WORKFLOW"
grep -q 'gh release create' "$TRANSACTION"
grep -q -- '--draft' "$TRANSACTION"
grep -q 'CREATE_ATTEMPTED=1' "$TRANSACTION"
grep -q 'gh release upload.*release/\*' "$TRANSACTION"
grep -q 'gh release download' "$TRANSACTION"
grep -q 'verify_published_release_roundtrip.py' "$TRANSACTION"
grep -q 'GITHUB-RELEASE-ROUNDTRIP.json' "$TRANSACTION"
grep -q 'GITHUB-RELEASE-FINAL-VERIFY.json' "$TRANSACTION"
grep -q 'github-release-expected' "$TRANSACTION"
grep -q 'gh release edit' "$TRANSACTION"
grep -q -- '--draft=false' "$TRANSACTION"
grep -q 'gh release delete' "$TRANSACTION"
grep -q -- '--json isDraft' "$TRANSACTION"
grep -q 'TRANSACTION_COMPLETE=1' "$TRANSACTION"
grep -q 'binario.marketing.github-release-roundtrip.v1' "$VERIFIER"

echo 'WAVE 93 DRAFT PUBLICATION TRANSACTION AUDIT PASS'
