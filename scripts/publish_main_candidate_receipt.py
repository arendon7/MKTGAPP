#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from typing import NamedTuple

CONTEXT = "physical-uat-candidate/main-artifact"
API_VERSION = "2022-11-28"
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
DIGEST_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class CandidateReceipt(NamedTuple):
    repository: str
    git_sha: str
    run_id: str
    artifact_id: str
    artifact_url: str
    artifact_digest: str


def _require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def _normalize_digest(value: str) -> str:
    digest = str(value or "").strip()
    if digest.lower().startswith("sha256:"):
        digest = digest.split(":", 1)[1]
    _require(bool(DIGEST_RE.fullmatch(digest)), "artifact digest must be SHA-256")
    return digest.lower()


def validate_receipt(
    *,
    repository: str,
    git_sha: str,
    event_name: str,
    git_ref: str,
    run_id: str,
    artifact_id: str,
    artifact_url: str,
    artifact_digest: str,
) -> CandidateReceipt:
    repository = str(repository or "").strip()
    git_sha = str(git_sha or "").strip().lower()
    event_name = str(event_name or "").strip()
    git_ref = str(git_ref or "").strip()
    run_id = str(run_id or "").strip()
    artifact_id = str(artifact_id or "").strip()
    artifact_url = str(artifact_url or "").strip()

    _require(bool(REPO_RE.fullmatch(repository)), "invalid repository identity")
    _require(bool(SHA_RE.fullmatch(git_sha)), "invalid git SHA")
    _require(event_name == "push", "candidate receipt is allowed only for push")
    _require(git_ref == "refs/heads/main", "candidate receipt is allowed only for refs/heads/main")
    _require(run_id.isdigit() and int(run_id) > 0, "invalid workflow run id")
    _require(artifact_id.isdigit() and int(artifact_id) > 0, "invalid artifact id")

    expected_url = f"https://github.com/{repository}/actions/runs/{run_id}/artifacts/{artifact_id}"
    _require(artifact_url == expected_url, "artifact URL is not bound to repository/run/artifact identity")

    digest = _normalize_digest(artifact_digest)
    return CandidateReceipt(
        repository=repository,
        git_sha=git_sha,
        run_id=run_id,
        artifact_id=artifact_id,
        artifact_url=artifact_url,
        artifact_digest=digest,
    )


def status_payload(receipt: CandidateReceipt) -> dict[str, str]:
    return {
        "state": "success",
        "target_url": receipt.artifact_url,
        "description": f"arm64 candidate uploaded; UAT not executed; sha256 {receipt.artifact_digest[:12]}",
        "context": CONTEXT,
    }


def publish_status(receipt: CandidateReceipt, *, token: str) -> dict:
    token = str(token or "").strip()
    _require(bool(token), "GITHUB_TOKEN is required")
    url = f"https://api.github.com/repos/{receipt.repository}/statuses/{receipt.git_sha}"
    payload = status_payload(receipt)
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "superbid-main-candidate-receipt",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"GitHub status API rejected candidate receipt: HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub status API unavailable: {exc.reason}") from exc

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub status API returned invalid JSON") from exc
    _require(isinstance(result, dict), "GitHub status API returned invalid object")
    _require(result.get("state") == "success", "published candidate receipt is not success")
    _require(result.get("context") == CONTEXT, "published candidate receipt context drift")
    _require(result.get("target_url") == receipt.artifact_url, "published candidate receipt target drift")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish a durable, non-UAT commit-status receipt for the exact arm64 candidate uploaded by push-main."
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--event", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact-url", required=True)
    parser.add_argument("--artifact-digest", required=True)
    args = parser.parse_args()

    receipt = validate_receipt(
        repository=args.repo,
        git_sha=args.sha,
        event_name=args.event,
        git_ref=args.ref,
        run_id=args.run_id,
        artifact_id=args.artifact_id,
        artifact_url=args.artifact_url,
        artifact_digest=args.artifact_digest,
    )
    publish_status(receipt, token=os.environ.get("GITHUB_TOKEN", ""))
    print(json.dumps({
        "schema": "superbid.physical-uat-main-candidate-receipt.v1",
        "git_sha": receipt.git_sha,
        "run_id": receipt.run_id,
        "artifact_id": receipt.artifact_id,
        "artifact_url": receipt.artifact_url,
        "artifact_digest": f"sha256:{receipt.artifact_digest}",
        "status_context": CONTEXT,
        "candidate_uploaded": True,
        "physical_uat_executed": False,
        "release_authority": False,
        "production_ready": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
