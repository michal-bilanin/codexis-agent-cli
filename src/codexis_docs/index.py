"""The Index: building it from Pages and searching it (ADR-0001)."""

import os
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import apsw

from codexis_docs import __version__
from codexis_docs.config import LANGUAGES
from codexis_docs.tokenizer import register_tokenizers


class IndexNotFoundError(Exception):
    """There is no Index file at the given path."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"No index found at {path}")
        self.path = path


class EmptyQueryError(ValueError):
    """The query contains no words."""


@dataclass(frozen=True)
class Result:
    title: str
    url: str
    snippet: str


def build_index(path: Path, pages: Iterable[tuple[str, str, str, str]]) -> None:
    """Replace the Index at `path` with one holding `pages`.

    Each Page is (url, lang, title, main_text). The new Index is written to a
    temporary file next to `path` and swapped in only when complete, so a
    failure leaves the existing Index untouched.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        con = _connect(tmp, apsw.SQLITE_OPEN_READWRITE | apsw.SQLITE_OPEN_CREATE)
        try:
            with con:
                _create_schema(con)
                for url, lang, title, main_text in pages:
                    _check_language(lang)
                    con.execute(
                        f"INSERT INTO pages_{lang}(url, title, text) VALUES (?, ?, ?)",
                        (url, title, main_text),
                    )
        finally:
            con.close()
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def search(
    path: Path,
    query: str,
    lang: str,
    limit: int,
    highlight: tuple[str, str] = ("", ""),
) -> list[Result]:
    """Return the Pages in `lang` matching every word of `query`, best first.

    Matched words in each Snippet are wrapped in the `highlight` markers.
    """
    _check_language(lang)
    words = query.split()
    if not words:
        raise EmptyQueryError("The query contains no words")
    try:
        con = _connect(path, apsw.SQLITE_OPEN_READONLY)
    except apsw.CantOpenError:
        raise IndexNotFoundError(path) from None
    try:
        rows = con.execute(
            f"SELECT title, url, snippet(pages_{lang}, 2, ?, ?, '…', 30)"
            f" FROM pages_{lang} WHERE pages_{lang} MATCH ?"
            f" ORDER BY bm25(pages_{lang}, 0, 5.0, 1.0) LIMIT ?",
            (*highlight, _match_expression(words), limit),
        ).fetchall()
    finally:
        con.close()
    # title, url and the Snippet are always text.
    return [Result(*cast(tuple[str, str, str], row)) for row in rows]


def _create_schema(con: apsw.Connection) -> None:
    con.execute("CREATE TABLE meta(crawled_at TEXT NOT NULL, version TEXT NOT NULL)")
    con.execute(
        "INSERT INTO meta VALUES (?, ?)",
        (datetime.now(UTC).isoformat(timespec="seconds"), __version__),
    )
    for lang in LANGUAGES:
        con.execute(
            f"CREATE VIRTUAL TABLE pages_{lang}"
            f" USING fts5(url UNINDEXED, title, text, tokenize='lemma_{lang}')"
        )


def _check_language(lang: str) -> None:
    # Languages name tables in SQL, so only supported codes may get that far.
    if lang not in LANGUAGES:
        raise ValueError(f"Unsupported language: {lang!r}")


def _match_expression(words: list[str]) -> str:
    # Each word becomes an FTS5 string literal, so no query syntax reaches the
    # engine; literals separated by spaces are an implicit AND.
    return " ".join('"' + word.replace('"', '""') + '"' for word in words)


def _connect(path: Path, flags: int) -> apsw.Connection:
    con = apsw.Connection(str(path), flags=flags)
    register_tokenizers(con)
    return con
