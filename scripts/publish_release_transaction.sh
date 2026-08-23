#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REF_NAME:?GITHUB_REF_NAME is required}"
: "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
: "${GITHUB_SHA:?GITHUB_SHA is required}"
: "${GH_TOKEN:?GH_TOKEN is required}"

test -f release/RELEASE-ARTIFACT-AUTHORIZATION.json

DRAFT_CREATED=0
cleanup() {
  status=$?
  if [[ $status -ne 0 && "$DRAFT_CREATED" == "1" ]]; then
    set +e
    is_draft="$(gh release view "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" --json isDraft --jq '.isDraft' 2>/dev/null)"
    if [[ "$is_draft" == "true" ]]; then
      gh release delete "$GITHUB_REF_NAME" --repo "$GITHUB_REPOSITORY" --yes
    fi
  fi
  exit "$status"
}
trap cleanup EXIT

gh release create "$GITHUB_REF_NAME" release/* \
  --repo "$GITHUB_REPOSITORY" \
  --verify-tag \
  --draft \
  --title "BINARIO Marketing $GITHUB_REF_NAME" \
  --generate-notes
DRAFT_CREATED=1

rm -rf github-release-roundtrip
mkdir -p github-release-roundtrip
gh release download "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --dir github-release-roundtrip

python scripts/verify_published_release_roundtrip.py \
  --expected-dir release \
  --downloaded-dir github-release-roundtrip \
  --tag "$GITHUB_REF_NAME" \
  --git-sha "$GITHUB_SHA" \
  --output release/GITHUB-RELEASE-ROUNDTRIP.json

gh release upload "$GITHUB_REF_NAME" release/GITHUB-RELEASE-ROUNDTRIP.json \
  --repo "$GITHUB_REPOSITORY" \
  --clobber

python scripts/verify_published_release_roundtrip.py \
  --expected-dir release \
  --downloaded-dir github-release-roundtrip \
  --tag "$GITHUB_REF_NAME" \
  --git-sha "$GITHUB_SHA" \
  --output release/GITHUB-RELEASE-ROUNDTRIP.json

gh release edit "$GITHUB_REF_NAME" \
  --repo "$GITHUB_REPOSITORY" \
  --draft=false

DRAFT_CREATED=0
trap - EXIT
echo "WAVE 93 GITHUB RELEASE TRANSACTION PASS: $GITHUB_REF_NAME"
