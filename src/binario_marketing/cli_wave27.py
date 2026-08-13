from __future__ import annotations

import argparse
import sys


def _serve(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="binario-marketing serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--open", action="store_true", dest="open_browser")
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args(argv)
    from .service_wave27 import serve
    serve(args.host, args.port, allow_network=args.allow_network, open_browser=args.open_browser)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "serve":
        return _serve(args[1:])
    from .cli import main as canonical_main
    return canonical_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
