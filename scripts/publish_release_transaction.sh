#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

test -f release/RELEASE-ARTIFACT-AUTHORIZATION.json
test -f release/RELEASE-CI-PROVENANCE-AUTHORIZATION.json

# W94_STAGE_PROVENANCE_HANDOFF
# This must run before any GitHub Release mutation. It verifies the W94 seal,
# exact release tag/commit and the SHA-256 of this transaction script itself.
python scripts/release_ci_provenance_authorization.py verify-transaction-handoff \
  --authorization release/RELEASE-CI-PROVENANCE-AUTHORIZATION.json \
  --transaction-script scripts/publish_release_transaction.sh \
  --expected-tag "$GITHUB_REF_NAME" \
  --expected-git-sha "$GITHUB_SHA"

# W93_STAGE_PREEXISTING_RELEASE_CHECK
# A pre-existing release for this tag is never owned by this transaction and
# therefore must never be deleted by cleanup.
if gh release view "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" >/dev/null 2>&1; then
  echo "GITHUB RELEASE TRANSACTION BLOCKED: release already exists for $GITHUB_REF_NAME" >&2
  exit 7
fi

CREATE_ATTEMPTED=0
TRANSACTION_COMPLETE=0
cleanup() {
  status=$?
  if [[ $status -ne 0 && "$CREATE_ATTEMPTED" == "1" && "$TRANSACTION_COMPLETE" != "1" ]]; then
    set +e
    is_draft="$(gh release view "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" --json isDraft --jq '.isDraft' 2>/dev/null)"
    if [[ "$is_draft" == "true" ]]; then
      # W93_STAGE_DRAFT_DELETE
      gh release delete "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" --yes
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

# Create the draft before uploading any bytes. CREATE_ATTEMPTED is set before
# the command so an ambiguous network failure after server-side creation is
# still cleaned up. The preflight above guarantees an observed draft is ours.
CREATE_ATTEMPTED=1
# W93_STAGE_DRAFT_CREATE
gh release create "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --verify-tag \
  --draft \
  --title "BINARIO Marketing $GITHUB_REF_NAME" \
  --generate-notes

# Upload the exact W92-authorized + W94-provenance-bound local release set only
# after cleanup authority is active. Partial upload failure leaves a draft that
# the trap deletes.
# W93_STAGE_AUTHORIZED_UPLOAD
gh release upload "$GITHUB_REF_NAME" release/* \
  --repo "$GITHUB_REPOSITORY"

rm -rf github-release-roundtrip github-release-final github-release-expected .release-transaction
mkdir -p github-release-roundtrip github-release-final github-release-expected .release-transaction

# W93_STAGE_AUTHORIZED_DOWNLOAD
gh release download "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --dir github-release-roundtrip

# First proof: every authorized local byte survived GitHub storage exactly.
# W93_STAGE_AUTHORIZED_VERIFY
python scripts/verify_published_release_roundtrip.py \
  --expected-dir release \
  --downloaded-dir github-release-roundtrip \
  --tag "$GITHUB_REF_NAME" \
  --git-sha "$GITHUB_SHA" \
  --output .release-transaction/GITHUB-RELEASE-ROUNDTRIP.json

# The round-trip evidence is deliberately non-authoritative, but it becomes a
# release asset. Build the intended final inventory and verify that inventory
# from a fresh GitHub download before publishing the draft.
cp release/* github-release-expected/
cp .release-transaction/GITHUB-RELEASE-ROUNDTRIP.json github-release-expected/

# W93_STAGE_EVIDENCE_UPLOAD
gh release upload "$GITHUB_REF_NAME" .release-transaction/GITHUB-RELEASE-ROUNDTRIP.json \
  --repo "$GITHUB_REPOSITORY"

# W93_STAGE_FINAL_DOWNLOAD
gh release download "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --dir github-release-final

# W93_STAGE_FINAL_VERIFY
python scripts/verify_published_release_roundtrip.py \
  --expected-dir github-release-expected \
  --downloaded-dir github-release-final \
  --tag "$GITHUB_REF_NAME" \
  --git-sha "$GITHUB_SHA" \
  --output .release-transaction/GITHUB-RELEASE-FINAL-VERIFY.json

# W93_STAGE_PUBLICATION
gh release edit "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --draft=false

TRANSACTION_COMPLETE=1
trap - EXIT
echo "WAVE 93 GITHUB RELEASE TRANSACTION PASS: $GITHUB_REF_NAME"
