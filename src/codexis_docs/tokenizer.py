"""Lemmatizing FTS5 tokenizers, one per Language (ADR-0001)."""

from collections.abc import Iterable
from functools import partial

import apsw
import apsw.fts5
import simplemma

from codexis_docs.config import LANGUAGES


def register_tokenizers(
    con: apsw.Connection, languages: Iterable[str] = LANGUAGES
) -> None:
    """Register an FTS5 tokenizer `lemma_<lang>` on `con` for every Language."""
    apsw.fts5.register_tokenizers(
        con,
        {
            "simplify": apsw.fts5.SimplifyTokenizer,
            "unicodewords": apsw.fts5.UnicodeWordsTokenizer,
        },
    )
    for lang in languages:
        con.register_fts5_tokenizer(
            f"lemmatize_{lang}",
            apsw.fts5.TransformTokenizer(partial(simplemma.lemmatize, lang=lang)),
        )
        con.register_fts5_tokenizer(
            f"lemma_{lang}", partial(_lemma_tokenizer, lang=lang)
        )


def _lemma_tokenizer(
    con: apsw.Connection, args: list[str], lang: str
) -> apsw.FTS5Tokenizer:
    # Read right to left: split words, casefold, lemmatize, strip diacritics.
    return con.fts5_tokenizer(
        "simplify",
        ["strip", "true", f"lemmatize_{lang}"]
        + ["simplify", "casefold", "true", "unicodewords", *args],
    )
