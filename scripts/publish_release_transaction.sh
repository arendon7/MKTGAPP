#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

test -f release/RELEASE-ARTIFACT-AUTHORIZATION.json

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
gh release create "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --verify-tag \
  --draft \
  --title "BINARIO Marketing $GITHUB_REF_NAME" \
  --generate-notes

# Upload the exact W92-authorized local release set only after cleanup authority
# is active. Partial upload failure leaves a draft that the trap deletes.
gh release upload "$GITHUB_REF_NAME" release/* \
  --repo "$GITHUB_REPOSITORY"

rm -rf github-release-roundtrip github-release-final github-release-expected .release-transaction
mkdir -p github-release-roundtrip github-release-final github-release-expected .release-transaction

gh release download "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --dir github-release-roundtrip

# First proof: every W92-authorized local byte survived GitHub storage exactly.
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

gh release upload "$GITHUB_REF_NAME" .release-transaction/GITHUB-RELEASE-ROUNDTRIP.json \
  --repo "$GITHUB_REPOSITORY"

gh release download "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --dir github-release-final

python scripts/verify_published_release_roundtrip.py \
  --expected-dir github-release-expected \
  --downloaded-dir github-release-final \
  --tag "$GITHUB_REF_NAME" \
  --git-sha "$GITHUB_SHA" \
  --output .release-transaction/GITHUB-RELEASE-FINAL-VERIFY.json

gh release edit "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --draft=false

TRANSACTION_COMPLETE=1
trap - EXIT
echo "WAVE 93 GITHUB RELEASE TRANSACTION PASS: $GITHUB_REF_NAME"
