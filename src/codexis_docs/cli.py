"""Command-line interface for codexis-docs."""

import argparse
import sys

from codexis_docs.config import LANGUAGES


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        number = 0
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codexis-docs",
        description="Crawl and search the CODEXIS AI documentation.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("crawl", help="Crawl the site and rebuild the Index.")

    search = commands.add_parser("search", help="Search the Index.")
    search.add_argument("query", help="Keywords that every Result must match.")
    search.add_argument(
        "--lang", required=True, choices=LANGUAGES, help="Language to search in."
    )
    search.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        help="Maximum number of Results (default: %(default)s).",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1
