import pytest

from codexis_docs.cli import main
from codexis_docs.config import HOME_ENV_VAR, index_path
from codexis_docs.index import build_index

UPLOAD_URL = "https://docs.codexis.ai/guide/nahravani-vlastnich-souboru/"

PAGES = [
    (
        UPLOAD_URL,
        "cs",
        "Nahrávání vlastních souborů",
        "Do konverzace můžete nahrát vlastní soubory. Nahrávání souborů podporuje"
        " formáty PDF a DOCX.",
    ),
    *(
        (
            f"https://docs.codexis.ai/guide/stranka-{number}/",
            "cs",
            f"Stránka {number}",
            "Nahrávání souborů je popsáno jinde, zde jen zmínka o souborech.",
        )
        for number in range(1, 8)
    ),
    (
        "https://docs.codexis.ai/guide/kredity-a-cenik/sdilene-ucty/",
        "cs",
        "Sdílený kreditový účet",
        "Sdílený účet umožňuje oddělení nebo týmu nakupovat a spravovat vlastní kredity.",
    ),
]


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv(HOME_ENV_VAR, str(tmp_path))
    return tmp_path


@pytest.fixture
def index(home):
    build_index(index_path(), PAGES)


def test_search_without_lang_is_a_usage_error(capsys):
    assert main(["search", "foo"]) == 2
    assert "--lang" in capsys.readouterr().err


def test_search_with_unsupported_lang_is_a_usage_error(capsys):
    assert main(["search", "foo", "--lang", "de"]) == 2
    assert "invalid choice: 'de'" in capsys.readouterr().err


def test_search_with_non_positive_limit_is_a_usage_error(capsys):
    assert main(["search", "foo", "--lang", "cs", "--limit", "0"]) == 2
    assert "argument --limit: must be a positive integer" in capsys.readouterr().err


@pytest.mark.parametrize("query", ["", "   "])
def test_search_with_no_words_is_a_usage_error(query, index, capsys):
    assert main(["search", query, "--lang", "cs"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "usage:" in captured.err
    assert "query contains no words" in captured.err


def test_search_prints_best_result_first_within_limit(index, capsys):
    assert main(["search", "nahrávání souborů", "--lang", "cs", "--limit", "5"]) == 0

    blocks = capsys.readouterr().out.rstrip("\n").split("\n\n")
    assert len(blocks) == 5
    assert blocks[0].splitlines()[:2] == [
        "1. Nahrávání vlastních souborů",
        f"   {UPLOAD_URL}",
    ]


def test_search_output_format(index, capsys):
    assert main(["search", "kredity", "--lang", "cs"]) == 0

    assert capsys.readouterr().out == (
        "1. Sdílený kreditový účet\n"
        "   https://docs.codexis.ai/guide/kredity-a-cenik/sdilene-ucty/\n"
        "   Sdílený účet umožňuje oddělení nebo týmu nakupovat a spravovat"
        " vlastní kredity.\n"
    )


def test_results_are_separated_by_one_blank_line(index, capsys):
    assert main(["search", "souborů", "--lang", "cs", "--limit", "2"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 7
    assert lines[3] == ""
    assert lines[4].startswith("2. ")
    assert lines[-1] != ""


def test_search_output_has_no_ansi_escapes_when_not_a_tty(index, capsys):
    assert main(["search", "nahrávání souborů", "--lang", "cs"]) == 0

    assert "\033" not in capsys.readouterr().out


def test_search_output_bolds_matches_on_a_tty(index, capsys, monkeypatch):
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)

    assert main(["search", "kredity", "--lang", "cs"]) == 0

    assert "\033[1mkredity\033[0m" in capsys.readouterr().out


def test_search_without_index_is_a_runtime_error(home, capsys):
    assert main(["search", "soubory", "--lang", "cs"]) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        f"No index found at {home / 'index.db'}. Run 'codexis-docs crawl' first.\n"
    )


def test_search_without_results_succeeds(index, capsys):
    assert main(["search", "neexistující slovo", "--lang", "en"]) == 0

    captured = capsys.readouterr()
    assert captured.out == 'No results for "neexistující slovo" (lang en).\n'
    assert captured.err == ""


def test_snippet_spanning_main_text_lines_is_printed_on_one_line(home, capsys):
    build_index(
        index_path(),
        [(UPLOAD_URL, "cs", "Soubory", "První odstavec o souborech.\nDruhý odstavec.")],
    )

    assert main(["search", "soubor", "--lang", "cs"]) == 0

    assert capsys.readouterr().out.splitlines() == [
        "1. Soubory",
        f"   {UPLOAD_URL}",
        "   První odstavec o souborech. Druhý odstavec.",
    ]
