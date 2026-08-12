#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__  # noqa: E402

TAG_RE = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9.-]+)?$")


def verify(tag: str) -> None:
    if not TAG_RE.fullmatch(tag):
        raise ValueError(f"invalid release tag format: {tag}")
    if not RELEASE_READY:
        raise ValueError("release publishing is disabled by the canonical version contract")
    if not RELEASE_TAG:
        raise ValueError("release publishing is enabled but RELEASE_TAG is unset")
    expected = f"v{__version__}"
    if RELEASE_TAG != expected:
        raise ValueError(f"canonical RELEASE_TAG drift: {RELEASE_TAG} != {expected}")
    if tag != RELEASE_TAG:
        raise ValueError(f"tag mismatch: {tag} != {RELEASE_TAG}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    args = parser.parse_args(argv)
    try:
        verify(args.tag)
    except ValueError as exc:
        print(f"RELEASE TAG BLOCKED: {exc}", file=sys.stderr)
        return 4
    print(f"RELEASE TAG PASS: {args.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
