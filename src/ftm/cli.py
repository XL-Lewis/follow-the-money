from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import Config
from .pipeline import run_fetch, run_parse
from .web import app as web_app


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data"),
        help="Where to store the SQLite DB and downloaded PDFs (default: ./data)",
    )
    common.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose logging"
    )

    parser = argparse.ArgumentParser(prog="ftm", parents=[common])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser(
        "fetch",
        parents=[common],
        help="Discover and download declarations (incremental).",
    )
    sub.add_parser(
        "parse",
        parents=[common],
        help="Parse downloaded PDFs into the declarations table.",
    )
    serve = sub.add_parser("serve", parents=[common], help="Run the web UI.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=5000)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    cfg = Config(data_dir=args.data_dir)

    if args.cmd == "fetch":
        run_fetch(cfg)
    elif args.cmd == "parse":
        run_parse(cfg)
    elif args.cmd == "serve":
        web_app.run(cfg, host=args.host, port=args.port)
    else:  # pragma: no cover - argparse enforces required subcommand
        parser.error(f"unknown command: {args.cmd}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
