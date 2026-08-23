#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.github-release-roundtrip.v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inventory(root: Path) -> dict[str, dict[str, Any]]:
    if not root.is_dir():
        raise ValueError(f"directory missing: {root}")
    rows: dict[str, dict[str, Any]] = {}
    for path in sorted(root.iterdir(), key=lambda p: p.name):
        if not path.is_file():
            raise ValueError(f"unexpected non-file entry: {path.name}")
        if path.name in rows:
            raise ValueError(f"duplicate asset name: {path.name}")
        rows[path.name] = {"sha256": _sha256(path), "size": path.stat().st_size}
    if not rows:
        raise ValueError(f"no release assets found: {root}")
    return rows


def verify(expected_dir: Path, downloaded_dir: Path, *, tag: str, git_sha: str) -> dict[str, Any]:
    expected = _inventory(expected_dir.resolve())
    downloaded = _inventory(downloaded_dir.resolve())
    if set(expected) != set(downloaded):
        missing = sorted(set(expected) - set(downloaded))
        unexpected = sorted(set(downloaded) - set(expected))
        raise ValueError(f"published asset inventory mismatch: missing={missing}, unexpected={unexpected}")

    mismatches: list[str] = []
    for name, local in expected.items():
        remote = downloaded[name]
        if local != remote:
            mismatches.append(name)
    if mismatches:
        raise ValueError(f"published asset byte mismatch: {sorted(mismatches)}")

    return {
        "schema": SCHEMA,
        "tag": tag,
        "git_sha": git_sha,
        "asset_count": len(expected),
        "assets": expected,
        "draft_roundtrip_verified": True,
        "github_uploaded_bytes_match_authorized_local_bytes": True,
        "release_authority": False,
        "publication_authority": False,
        "production_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify exact GitHub Release draft assets against authorized local bytes.")
    parser.add_argument("--expected-dir", type=Path, required=True)
    parser.add_argument("--downloaded-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--git-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify(args.expected_dir, args.downloaded_dir, tag=args.tag, git_sha=args.git_sha)
    except ValueError as exc:
        raise SystemExit(f"GITHUB RELEASE ROUNDTRIP BLOCKED: {exc}") from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
