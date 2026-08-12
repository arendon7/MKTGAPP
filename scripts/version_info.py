#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from binario_marketing.version import (  # noqa: E402
    MACOS_BUNDLE_VERSION,
    MACOS_SHORT_VERSION,
    RELEASE_READY,
    RELEASE_TAG,
    __version__,
)


def payload() -> dict:
    return {
        "version": __version__,
        "macos_short_version": MACOS_SHORT_VERSION,
        "macos_bundle_version": MACOS_BUNDLE_VERSION,
        "release_ready": RELEASE_READY,
        "release_tag": RELEASE_TAG,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--field", choices=tuple(payload().keys()))
    args = parser.parse_args(argv)
    data = payload()
    if args.field:
        value = data[args.field]
        if value is None:
            return 2
        if isinstance(value, bool):
            print("true" if value else "false")
        else:
            print(value)
    else:
        print(json.dumps(data, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
