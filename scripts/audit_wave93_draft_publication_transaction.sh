#!/usr/bin/env bash
set -euo pipefail

WORKFLOW=.github/workflows/persistent-release.yml
TRANSACTION=scripts/publish_release_transaction.sh
VERIFIER=scripts/verify_published_release_roundtrip.py

test -f "$WORKFLOW"
test -f "$TRANSACTION"
test -f "$VERIFIER"

grep -q 'bash scripts/publish_release_transaction.sh' "$WORKFLOW"
! grep -q 'Publish permanent GitHub Release' "$WORKFLOW"
grep -q 'gh release create' "$TRANSACTION"
grep -q -- '--draft' "$TRANSACTION"
grep -q 'gh release download' "$TRANSACTION"
grep -q 'verify_published_release_roundtrip.py' "$TRANSACTION"
grep -q 'gh release upload' "$TRANSACTION"
grep -q 'gh release edit' "$TRANSACTION"
grep -q -- '--draft=false' "$TRANSACTION"
grep -q 'gh release delete' "$TRANSACTION"

echo 'WAVE 93 DRAFT PUBLICATION TRANSACTION AUDIT PASS'
