import apsw
import pytest

from codexis_docs.tokenizer import register_tokenizers


@pytest.fixture
def con():
    connection = apsw.Connection(":memory:")
    register_tokenizers(connection)
    return connection


def tokens(con, lang, text):
    tokenizer = con.fts5_tokenizer(f"lemma_{lang}")
    return [
        tuple(rest)
        for _start, _end, *rest in tokenizer(
            text.encode(), apsw.FTS5_TOKENIZE_DOCUMENT, None
        )
    ]


def test_cs_inflected_phrase_gives_same_tokens_as_base_form(con):
    assert tokens(con, "cs", "sdíleného účtu") == tokens(con, "cs", "Sdílený účet")
    assert tokens(con, "cs", "souborů") == tokens(con, "cs", "soubor")


def test_sk_inflected_phrase_gives_same_tokens_as_base_form(con):
    assert tokens(con, "sk", "zdieľaných účtov") == tokens(con, "sk", "zdieľaný účet")


def test_en_plural_gives_same_token_as_singular(con):
    assert tokens(con, "en", "accounts") == tokens(con, "en", "account")


def test_diacritics_are_folded(con):
    assert tokens(con, "cs", "ucet") == tokens(con, "cs", "účet")


def test_highlight_shows_original_inflected_words(con):
    con.execute("CREATE VIRTUAL TABLE pages USING fts5(text, tokenize='lemma_cs')")
    con.execute(
        "INSERT INTO pages VALUES (?)",
        ("Sdílený účet umožňuje nahrávání souborů.",),
    )

    (highlighted,) = con.execute(
        "SELECT highlight(pages, 0, '[', ']') FROM pages WHERE pages MATCH ?",
        ('"sdíleného" "účty" "soubor"',),
    ).fetchone()

    assert highlighted == "[Sdílený] [účet] umožňuje nahrávání [souborů]."


def test_any_simplemma_language_can_be_registered():
    con = apsw.Connection(":memory:")
    register_tokenizers(con, languages=("pl",))

    assert tokens(con, "pl", "plików") == tokens(con, "pl", "plik")
