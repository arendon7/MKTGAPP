from __future__ import annotations

import argparse
import json
from pathlib import Path

from .config import default_paths
from .hub import discover_apps
from .providers import PROVIDERS, diagnose_provider
from .runtime_center import diagnose


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="binario-marketing")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("apps")
    sub.add_parser("runtime")
    sub.add_parser("providers")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    if args.command == "apps":
        print(json.dumps([app.__dict__ | {"path": str(app.path)} for app in discover_apps(repo_root)], ensure_ascii=False, indent=2))
    elif args.command == "runtime":
        print(json.dumps([item.__dict__ for item in diagnose()], ensure_ascii=False, indent=2))
    elif args.command == "providers":
        print(json.dumps([diagnose_provider(item.id) for item in PROVIDERS], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
