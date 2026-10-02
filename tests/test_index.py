import pytest

from codexis_docs.index import (
    EmptyQueryError,
    IndexNotFoundError,
    build_index,
    search,
)

PAGES = [
    (
        "https://docs.codexis.ai/guide/kredity-a-cenik/sdilene-ucty/",
        "cs",
        "Sdílený kreditový účet",
        "Sdílený účet umožňuje oddělení nebo týmu nakupovat a spravovat vlastní kredity.",
    ),
    (
        "https://docs.codexis.ai/guide/nahravani-souboru/",
        "cs",
        "Nahrávání souborů",
        "Do konverzace můžete nahrát soubory ve formátu PDF nebo DOCX.",
    ),
    (
        "https://docs.codexis.ai/en/guide/credits-and-pricing/shared-accounts/",
        "en",
        "Shared credit account",
        "A shared account lets a department or team buy and manage its own credits.",
    ),
    (
        "https://docs.codexis.ai/sk/guide/kredity-a-cennik/zdielane-ucty/",
        "sk",
        "Zdieľaný kreditový účet",
        "Zdieľaný účet umožňuje oddeleniu alebo tímu nakupovať a spravovať vlastné kredity.",
    ),
]


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "index.db"
    build_index(path, PAGES)
    return path


def urls(results):
    return [result.url for result in results]


def test_inflected_query_finds_page(index):
    results = search(index, "sdíleného účtu", "cs", limit=10)

    assert [result.title for result in results] == ["Sdílený kreditový účet"]
    assert urls(results) == [
        "https://docs.codexis.ai/guide/kredity-a-cenik/sdilene-ucty/"
    ]


def test_every_keyword_must_match(index):
    assert urls(search(index, "soubory PDF", "cs", limit=10)) == [
        "https://docs.codexis.ai/guide/nahravani-souboru/"
    ]
    assert search(index, "soubory kredity", "cs", limit=10) == []


def test_title_match_outranks_body_only_match(tmp_path):
    path = tmp_path / "index.db"
    build_index(
        path,
        [
            (
                "https://docs.codexis.ai/guide/body/",
                "cs",
                "Práce s dokumenty",
                "Konverzace začíná dotazem. Každá konverzace má historii a konverzaci"
                " lze sdílet.",
            ),
            (
                "https://docs.codexis.ai/guide/title/",
                "cs",
                "Nová konverzace",
                "Tlačítkem vlevo nahoře začnete znovu s prázdným oknem a novým dotazem.",
            ),
        ],
    )

    assert urls(search(path, "konverzace", "cs", limit=10)) == [
        "https://docs.codexis.ai/guide/title/",
        "https://docs.codexis.ai/guide/body/",
    ]


def test_search_returns_only_pages_of_the_requested_language(tmp_path):
    path = tmp_path / "index.db"
    build_index(
        path,
        [
            ("https://docs.codexis.ai/guide/a/", "cs", "CODEXIS AI", "Úvod."),
            ("https://docs.codexis.ai/en/guide/a/", "en", "CODEXIS AI", "Intro."),
            ("https://docs.codexis.ai/sk/guide/a/", "sk", "CODEXIS AI", "Úvod."),
        ],
    )

    assert urls(search(path, "codexis", "en", limit=10)) == [
        "https://docs.codexis.ai/en/guide/a/"
    ]


@pytest.mark.parametrize(
    "query",
    ['"soubory', "soubory*", "-soubory", "soubory:", "(soubory", "soubory)"],
)
def test_fts5_syntax_characters_are_treated_as_part_of_words(index, query):
    assert urls(search(index, query, "cs", limit=10)) == [
        "https://docs.codexis.ai/guide/nahravani-souboru/"
    ]


@pytest.mark.parametrize("operator", ["AND", "OR", "NOT", "NEAR"])
def test_fts5_operators_are_keywords_that_must_match(index, operator):
    assert search(index, f"soubory {operator} PDF", "cs", limit=10) == []


def test_search_without_index_raises_and_creates_nothing(tmp_path):
    path = tmp_path / "index.db"

    with pytest.raises(IndexNotFoundError) as excinfo:
        search(path, "soubory", "cs", limit=10)

    assert excinfo.value.path == path
    assert not path.exists()


@pytest.mark.parametrize("query", ["", "   ", "\t\n"])
def test_query_without_words_is_rejected(index, query):
    with pytest.raises(EmptyQueryError):
        search(index, query, "cs", limit=10)


def test_snippet_wraps_original_words_in_given_markers(index):
    (result,) = search(index, "sdíleného účtu", "cs", limit=10, highlight=("[", "]"))

    assert result.snippet == (
        "[Sdílený] [účet] umožňuje oddělení nebo týmu nakupovat a spravovat"
        " vlastní kredity."
    )


def test_snippet_has_no_markers_by_default(index):
    (result,) = search(index, "sdíleného účtu", "cs", limit=10)

    assert result.snippet == (
        "Sdílený účet umožňuje oddělení nebo týmu nakupovat a spravovat"
        " vlastní kredity."
    )


def test_limit_caps_the_number_of_results(tmp_path):
    path = tmp_path / "index.db"
    build_index(
        path,
        [
            (f"https://docs.codexis.ai/guide/{n}/", "cs", f"Kredity {n}", "Text.")
            for n in range(5)
        ],
    )

    assert len(search(path, "kredity", "cs", limit=3)) == 3


def test_snippet_of_long_text_is_an_excerpt_around_the_match(tmp_path):
    path = tmp_path / "index.db"
    filler = " ".join(["slovo"] * 100)
    build_index(
        path,
        [
            (
                "https://docs.codexis.ai/guide/a/",
                "cs",
                "Dlouhá stránka",
                f"{filler} Sdílený účet. {filler}",
            )
        ],
    )

    (result,) = search(path, "účet", "cs", limit=10, highlight=("[", "]"))

    assert result.snippet.startswith("…")
    assert result.snippet.endswith("…")
    assert "[účet]" in result.snippet
    assert len(result.snippet.split()) <= 30


def test_rebuild_replaces_the_previous_index(index):
    build_index(
        index,
        [("https://docs.codexis.ai/guide/new/", "cs", "Nová stránka", "Soubory.")],
    )

    assert urls(search(index, "soubory", "cs", limit=10)) == [
        "https://docs.codexis.ai/guide/new/"
    ]
    assert list(index.parent.iterdir()) == [index]


def test_failing_build_leaves_previous_index_untouched(index):
    before = index.read_bytes()

    def pages():
        yield ("https://docs.codexis.ai/guide/new/", "cs", "Nová stránka", "Text.")
        raise RuntimeError("crawl aborted")

    with pytest.raises(RuntimeError, match="crawl aborted"):
        build_index(index, pages())

    assert index.read_bytes() == before
    assert list(index.parent.iterdir()) == [index]


def test_build_creates_the_index_directory(tmp_path):
    path = tmp_path / "home" / "index.db"

    build_index(path, PAGES)

    assert len(search(path, "soubory", "cs", limit=10)) == 1


def test_page_in_unsupported_language_fails_the_build(index):
    before = index.read_bytes()

    with pytest.raises(ValueError, match="'de'"):
        build_index(index, [("https://docs.codexis.ai/de/", "de", "Titel", "Text.")])

    assert index.read_bytes() == before


def test_search_in_unsupported_language_is_rejected(index):
    with pytest.raises(ValueError, match="'de'"):
        search(index, "soubory", "de", limit=10)


def test_language_without_pages_has_no_results(tmp_path):
    path = tmp_path / "index.db"
    build_index(path, [("https://docs.codexis.ai/guide/a/", "cs", "Úvod", "Text.")])

    assert search(path, "text", "sk", limit=10) == []
