from __future__ import annotations

import argparse
import getpass
import json
import os
from dataclasses import asdict
from pathlib import Path

from .hub import discover_apps
from .meta_credentials import MetaCredentialStore
from .meta_graph import MetaGraphClient
from .providers import PROVIDERS, diagnose_provider
from .runtime_center import diagnose


def _meta_version() -> str:
    return os.environ.get("META_GRAPH_API_VERSION", "v25.0").strip() or "v25.0"


def _meta_status_payload() -> dict:
    status = MetaGraphClient.diagnose_env()
    return asdict(status)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="binario-marketing")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("apps")
    sub.add_parser("runtime")
    sub.add_parser("providers")
    sub.add_parser("meta-status", help="show Meta connection readiness without exposing the token")
    connect_parser = sub.add_parser("meta-connect", help="validate and save a Meta token in native Keychain")
    connect_parser.add_argument("--stdin", action="store_true", help="read the token from stdin instead of a hidden prompt")
    sub.add_parser("meta-disconnect", help="remove the app-managed Meta token from native Keychain")
    serve_parser = sub.add_parser("serve", help="run the local BINARIO Marketing web app")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", type=int, default=8765)
    serve_parser.add_argument("--open", action="store_true", dest="open_browser")
    serve_parser.add_argument("--allow-network", action="store_true")
    dev_parser = sub.add_parser("serve-dev", help="run the isolated post-W99 development runtime without changing the frozen release runtime")
    dev_parser.add_argument("--host", default="127.0.0.1")
    dev_parser.add_argument("--port", type=int, default=8766)
    dev_parser.add_argument("--open", action="store_true", dest="open_browser")
    dev_parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    if args.command == "apps":
        print(json.dumps([app.__dict__ | {"path": str(app.path)} for app in discover_apps(repo_root)], ensure_ascii=False, indent=2))
    elif args.command == "runtime":
        print(json.dumps([item.__dict__ for item in diagnose()], ensure_ascii=False, indent=2))
    elif args.command == "providers":
        print(json.dumps([diagnose_provider(item.id) for item in PROVIDERS], ensure_ascii=False, indent=2))
    elif args.command == "meta-status":
        print(json.dumps(_meta_status_payload(), ensure_ascii=False, indent=2))
    elif args.command == "meta-connect":
        token = (os.sys.stdin.read() if args.stdin else getpass.getpass("Meta access token: ")).strip()
        if not token:
            parser.error("Meta access token is required")
        identity = MetaGraphClient(token, _meta_version()).identity()
        status = MetaCredentialStore().write(token)
        print(json.dumps({"connected": True, "source": status.source, "identity": identity}, ensure_ascii=False, indent=2))
    elif args.command == "meta-disconnect":
        status = MetaCredentialStore().delete()
        print(json.dumps({"connected": status.configured, "source": status.source}, ensure_ascii=False, indent=2))
    elif args.command == "serve":
        from .service import serve
        serve(args.host, args.port, allow_network=args.allow_network, open_browser=args.open_browser)
    elif args.command == "serve-dev":
        from .service_post_w99_dev_app import serve
        serve(args.host, args.port, allow_network=args.allow_network, open_browser=args.open_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
