"""Command-line interface for codexis-docs."""

import argparse
import sys
from collections import Counter
from collections.abc import Iterator
from pathlib import Path

import httpx

from codexis_docs.config import LANGUAGES, index_path
from codexis_docs.crawler import Crawler, make_client
from codexis_docs.extract import Skipped, extract
from codexis_docs.index import IndexNotFoundError, Result, build_index, search

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


def main(
    argv: list[str] | None = None, *, transport: httpx.BaseTransport | None = None
) -> int:
    """Run the CLI and return its exit code; `transport` replaces the network."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "search" and not args.query.split():
            parser.error("the query contains no words")
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    if args.command == "search":
        return _search(args.query, args.lang, args.limit)
    return _crawl(transport)


class CrawlAborted(Exception):
    """Docs-section URLs failed, so the Crawl must not replace the Index."""

    def __init__(self, urls: list[str]) -> None:
        super().__init__(f"{len(urls)} Docs-section URLs failed")
        self.urls = urls


def _crawl(transport: httpx.BaseTransport | None) -> int:
    """Crawl the site into a new Index and return the exit code."""
    path = index_path()
    status = _Status()
    counts = Counter({lang: 0 for lang in LANGUAGES})
    with make_client(transport) as client:
        crawler = Crawler(
            client,
            on_warning=status.warn,
            on_progress=lambda fetched, queued: status.progress(
                f"Crawling: {fetched} fetched, {queued} queued,"
                f" {counts.total()} pages"
            ),
        )

        def pages() -> Iterator[tuple[str, str, str, str]]:
            for url, html in crawler.pages():
                page = extract(html, url)
                if isinstance(page, Skipped):
                    status.warn(f"Skipped {url}: {page.reason}")
                    continue
                counts[page.lang] += 1
                yield url, page.lang, page.title, page.main_text
            # Raised inside build_index, before the swap, so it keeps the Index.
            if crawler.failures:
                raise CrawlAborted(crawler.failures)

        try:
            build_index(path, pages())
        except CrawlAborted as exc:
            status.done()
            failed = "".join(f"\n  {url}" for url in exc.urls)
            print(
                f"Crawl aborted: {len(exc.urls)} Docs-section URLs failed:{failed}"
                f"\nThe Index at {_display(path)} was left untouched.",
                file=sys.stderr,
            )
            return 1
    status.done()
    per_lang = ", ".join(f"{lang} {counts[lang]}" for lang in LANGUAGES)
    print(
        f"Indexed {counts.total()} pages ({per_lang}) into {_display(path)}",
        file=sys.stderr,
    )
    return 0


class _Status:
    """The progress line and warnings on stderr.

    On a TTY the progress line is redrawn in place and cleared before each
    warning; otherwise every update is a line of its own.
    """

    def __init__(self) -> None:
        self._tty = sys.stderr.isatty()
        self._shown = False

    def progress(self, line: str) -> None:
        if self._tty:
            sys.stderr.write(f"\r\033[K{line}")
            sys.stderr.flush()
            self._shown = True
        else:
            print(line, file=sys.stderr)

    def warn(self, message: str) -> None:
        self.done()
        print(f"Warning: {message}", file=sys.stderr)

    def done(self) -> None:
        if self._shown:
            sys.stderr.write("\r\033[K")
            self._shown = False


def _display(path: Path) -> str:
    """Show `path` relative to the home directory as `~/…` when it is inside."""
    try:
        return f"~/{path.relative_to(Path.home())}"
    except ValueError:
        return str(path)


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
    # The Snippet may span several lines of Main text; show it as one.
    snippet = " ".join(result.snippet.split())
    return f"{number}. {result.title}\n   {result.url}\n   {snippet}"
