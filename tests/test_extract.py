from collections import Counter, defaultdict

import pytest

from codexis_docs.extract import Extracted, Skipped, extract
from fixture_pages import FIXTURE_URLS, load

SDILENE_UCTY = "guide--kredity-a-cenik--sdilene-ucty.html"
URL = "https://docs.codexis.ai/guide/a/"
# Fixture pages in Docs sections; funkce.html is a marketing page.
DOCS_FIXTURES = [name for name in FIXTURE_URLS if name != "funkce.html"]


def extract_fixture(name):
    result = extract(load(name), FIXTURE_URLS[name])
    assert isinstance(result, Extracted), result
    return result


def test_docs_page_title_and_language():
    page = extract_fixture(SDILENE_UCTY)

    assert page.title == "Sdílený kreditový účet"
    assert page.lang == "cs"


def test_main_text_starts_with_the_lead_paragraph():
    page = extract_fixture(SDILENE_UCTY)

    assert page.main_text.startswith(
        "Sdílený účet umožňuje oddělení nebo týmu nakupovat a spravovat vlastní"
        " kredity nezávisle na hlavní licenci.\n"
    )


def test_main_text_keeps_prose_with_links_and_figcaptions():
    lines = extract_fixture(SDILENE_UCTY).main_text.splitlines()

    assert "Kam dál" in lines
    assert (
        "Limity, žádosti o kredity a historii čerpání popisuje stránka Správa"
        " kreditů. Nabídku balíčků najdete na stránce Kreditové balíčky."
    ) in lines
    assert "Sekce Sdílené účty s tlačítkem Nový účet" in lines
    assert "Pozastavený stav účtu" in lines


def test_main_text_has_no_boilerplate():
    text = extract_fixture(SDILENE_UCTY).main_text

    assert "Průvodce CODEXIS AI" not in text
    assert "Copy Anchor Link" not in text
    assert "schema.org" not in text
    assert "Aplikace Správa kreditů (Credit Management) umožňuje" not in text
    assert "Modely a kreditové sazby" not in text


def test_main_text_has_one_line_per_block_without_empty_lines():
    lines = extract_fixture(SDILENE_UCTY).main_text.splitlines()

    assert "Klikněte na Nový účet." in lines
    assert all(line and line == " ".join(line.split()) for line in lines)


@pytest.mark.parametrize(
    ("name", "lang", "title"),
    [
        (
            "en--guide--kredity-a-cenik--sdilene-ucty.html",
            "en",
            "Shared credit account",
        ),
        (
            "sk--guide--kredity-a-cenik--sdilene-ucty.html",
            "sk",
            "Zdieľaný kreditový účet",
        ),
    ],
)
def test_translations_have_their_language_and_title(name, lang, title):
    page = extract_fixture(name)

    assert (page.lang, page.title) == (lang, title)


def test_page_without_article_falls_back_to_main():
    page = extract_fixture("funkce.html")

    assert page.title == "Pomocník ve vaší každodenní praxi"
    assert page.main_text.startswith("Od analýzy dokumentů přes právní rešerši")


def test_every_fixture_page_has_title_and_main_text():
    for name in FIXTURE_URLS:
        page = extract_fixture(name)
        assert page.title, name
        assert page.main_text, name
        assert page.title not in page.main_text.splitlines(), name


def test_main_text_lines_do_not_repeat_across_pages_of_a_language():
    pages_by_lang = defaultdict(list)
    for name in DOCS_FIXTURES:
        page = extract_fixture(name)
        pages_by_lang[page.lang].append(set(page.main_text.splitlines()))

    for lang, pages in pages_by_lang.items():
        # A line on a single Page is never repetition, however few Pages there are.
        limit = max(1, 0.3 * len(pages))
        counts = Counter(line for lines in pages for line in lines if len(line) >= 40)
        assert [line for line, n in counts.items() if n > limit] == [], lang


def html_page(body, lang="cs"):
    return (
        f'<html lang="{lang}"><head><title>Stránka | CODEXIS AI</title></head>'
        f"<body>{body}</body></html>"
    )


def extract_html(html):
    result = extract(html, URL)
    assert isinstance(result, Extracted), result
    return result


def test_unsupported_language_is_skipped():
    html = html_page("<article><h1>Titel</h1><p>Text.</p></article>", "de")

    result = extract(html, URL)

    assert isinstance(result, Skipped)
    assert "'de'" in result.reason


def test_missing_language_is_skipped():
    html = "<html><body><article><h1>Titel</h1><p>Text.</p></article></body></html>"

    assert isinstance(extract(html, URL), Skipped)


def test_page_without_article_or_main_is_skipped():
    result = extract(html_page("<div><h1>Nadpis</h1><p>Text.</p></div>"), URL)

    assert isinstance(result, Skipped)
    assert "<article>" in result.reason and "<main>" in result.reason


def test_language_uses_the_primary_subtag_only():
    html = html_page("<article><h1>Nadpis</h1><p>Text.</p></article>", "cs-CZ")

    assert extract_html(html).lang == "cs"


def test_several_articles_fall_back_to_main():
    html = html_page(
        "<main><h1>Novinky</h1><article><p>První.</p></article>"
        "<article><p>Druhá.</p></article></main>"
    )

    assert extract_html(html).main_text == "První.\nDruhá."


def test_title_falls_back_to_title_element_without_site_suffix():
    html = html_page("<article><p>Text.</p></article>")

    page = extract_html(html)

    assert page.title == "Stránka"
    assert page.main_text == "Text."


def test_everything_before_a_nested_h1_is_removed():
    html = html_page(
        "<article><div><span>Drobečky</span><div><p>Úvod</p><h1>Nadpis</h1>"
        "<p>Perex.</p></div></div><p>Text.</p></article>"
    )

    assert extract_html(html).main_text == "Perex.\nText."


def test_link_dense_blocks_are_removed_but_prose_with_links_stays():
    html = html_page(
        "<article><h1>Nadpis</h1>"
        '<p>Postup popisuje stránka <a href="/a/">Správa kreditů</a> v detailu.</p>'
        '<ul><li><a href="/b/">Další stránka</a></li><li><a href="/c/">Jiná</a></li>'
        "</ul>"
        '<div><a href="/d/"><p>Předchozí</p><p>Perex sousední stránky.</p></a></div>'
        '<a href="/e/"><p>Další</p><p>Perex další stránky.</p></a>'
        "</article>"
    )

    assert extract_html(html).main_text == (
        "Postup popisuje stránka Správa kreditů v detailu."
    )


def test_structural_elements_are_removed_but_figcaptions_stay():
    html = html_page(
        "<article><h1>Nadpis</h1><nav>Menu</nav><p>Text"
        "<button>Copy Anchor Link</button></p>"
        '<script type="application/ld+json">{"@context":"https://schema.org"}</script>'
        '<figure><img alt="Obrázek"><figcaption>Popisek obrázku</figcaption></figure>'
        "<footer>Patička</footer></article>"
    )

    assert extract_html(html).main_text == "Text\nPopisek obrázku"
