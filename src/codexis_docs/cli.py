"""Command-line interface for codexis-docs."""

import argparse
import sys

from codexis_docs.config import LANGUAGES, index_path
from codexis_docs.index import IndexNotFoundError, Result, search

BOLD = ("\033[1m", "\033[0m")


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
        if args.command == "search" and not args.query.split():
            parser.error("the query contains no words")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    if args.command == "search":
        return _search(args.query, args.lang, args.limit)
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


def _search(query: str, lang: str, limit: int) -> int:
    """Print the Results for `query` and return the exit code."""
    path = index_path()
    highlight = BOLD if sys.stdout.isatty() else ("", "")
    try:
        results = search(path, query, lang, limit, highlight)
    except IndexNotFoundError:
        print(
            f"No index found at {path}. Run 'codexis-docs crawl' first.",
            file=sys.stderr,
        )
        return 1
    if not results:
        print(f'No results for "{query}" (lang {lang}).')
    else:
        blocks = (_format(n, result) for n, result in enumerate(results, start=1))
        print("\n\n".join(blocks))
    return 0


def _format(number: int, result: Result) -> str:
    """Render one Result as its numbered Title, then URL and Snippet indented."""
    return f"{number}. {result.title}\n   {result.url}\n   {result.snippet}"
