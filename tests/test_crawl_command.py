"""End to end: `crawl` against a fake site, then `search` the new Index."""

import httpx
import pytest

from codexis_docs.cli import main
from fixture_pages import FIXTURE_URLS, load

BASE = "https://docs.codexis.ai"
PAGE_URLS = {url: name for name, url in FIXTURE_URLS.items()}
LINKS = "".join(f'<a href="{url}">x</a>' for url in FIXTURE_URLS.values())
SEED_HTML = f'<html lang="cs"><body><main>{LINKS}</main></body></html>'
FAILING_URL = f"{BASE}/guide/rychly-start/"


def fake_site(failing: str | None = None) -> httpx.MockTransport:
    """Serve the fixture Pages, linked from every seed; anything else is 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == failing:
            return httpx.Response(503)
        if url in (f"{BASE}/", f"{BASE}/en/", f"{BASE}/sk/"):
            return httpx.Response(200, html=SEED_HTML)
        if url in PAGE_URLS:
            return httpx.Response(200, html=load(PAGE_URLS[url]))
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CODEXIS_DOCS_HOME", str(tmp_path))
    monkeypatch.setattr("codexis_docs.crawler.time.sleep", lambda seconds: None)
    return tmp_path


def test_crawl_indexes_docs_pages_and_prints_summary(home, capsys):
    assert main(["crawl"], transport=fake_site()) == 0

    err = capsys.readouterr().err
    assert (home / "index.db").exists()
    assert list(home.iterdir()) == [home / "index.db"]
    assert f"Indexed 10 pages (cs 8, en 1, sk 1) into {home / 'index.db'}" in err


def test_crawl_then_search_finds_the_page(home, capsys):
    assert main(["crawl"], transport=fake_site()) == 0
    capsys.readouterr()

    assert main(["search", "nahrávání souborů", "--lang", "cs", "--limit", "5"]) == 0

    out = capsys.readouterr().out
    results = out.split("\n\n")
    assert 1 <= len(results) <= 5
    title, url, snippet = results[0].splitlines()
    assert title == "1. Nahrávání vlastních souborů"
    assert url == f"   {BASE}/guide/nahravani-vlastnich-souboru/"
    assert "soubor" in snippet.lower()


@pytest.mark.parametrize(
    ("query", "lang", "url"),
    [
        ("sdílený kreditový účet", "cs", f"{BASE}/guide/kredity-a-cenik/sdilene-ucty/"),
        ("shared credit account", "en", f"{BASE}/en/guide/kredity-a-cenik/sdilene-ucty/"),
        ("zdieľaný kreditový účet", "sk", f"{BASE}/sk/guide/kredity-a-cenik/sdilene-ucty/"),
    ],
)
def test_crawl_then_search_each_language(home, capsys, query, lang, url):
    assert main(["crawl"], transport=fake_site()) == 0
    capsys.readouterr()

    assert main(["search", query, "--lang", lang]) == 0

    assert capsys.readouterr().out.splitlines()[1] == f"   {url}"


def test_404_links_are_warnings(home, capsys):
    assert main(["crawl"], transport=fake_site()) == 0

    assert "HTTP 404" in capsys.readouterr().err


def test_docs_failure_aborts_and_keeps_the_old_index(home, capsys):
    assert main(["crawl"], transport=fake_site()) == 0
    before = (home / "index.db").read_bytes()
    capsys.readouterr()

    assert main(["crawl"], transport=fake_site(failing=FAILING_URL)) == 1

    err = capsys.readouterr().err
    assert "Crawl aborted" in err
    assert f"  {FAILING_URL}" in err.splitlines()
    assert "Indexed" not in err
    assert (home / "index.db").read_bytes() == before
    assert list(home.iterdir()) == [home / "index.db"]


def test_docs_failure_on_first_crawl_creates_no_index(home):
    assert main(["crawl"], transport=fake_site(failing=FAILING_URL)) == 1

    assert list(home.iterdir()) == []


def test_skipped_page_is_a_warning(home, capsys):
    german = '<html lang="de"><body><article><h1>Hallo</h1></article></body></html>'

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/guide/de/":
            return httpx.Response(200, html=german)
        if request.url.path == "/":
            return httpx.Response(200, html='<a href="/guide/de/">de</a>')
        return httpx.Response(404)

    assert main(["crawl"], transport=httpx.MockTransport(handler)) == 0

    err = capsys.readouterr().err
    assert f"Skipped {BASE}/guide/de/: unsupported language 'de'" in err
    assert "Indexed 0 pages (cs 0, en 0, sk 0)" in err


def test_progress_is_one_line_per_fetch_without_a_tty(home, capsys):
    assert main(["crawl"], transport=fake_site()) == 0

    err = capsys.readouterr().err
    assert "\r" not in err
    assert any(line.startswith("Crawling: ") for line in err.splitlines())


def test_progress_overwrites_itself_on_a_tty(home, capsys, monkeypatch):
    monkeypatch.setattr("sys.stderr.isatty", lambda: True)

    assert main(["crawl"], transport=fake_site()) == 0

    err = capsys.readouterr().err
    assert "\r\033[KCrawling: " in err
    assert err.endswith("\n")
    assert "\nCrawling: " not in err


def test_crawl_uses_the_network_client_by_default(monkeypatch):
    seen = []

    def fake_make_client(transport=None):
        seen.append(transport)
        raise RuntimeError("stop")

    monkeypatch.setattr("codexis_docs.cli.make_client", fake_make_client)

    with pytest.raises(RuntimeError, match="stop"):
        main(["crawl"])

    assert seen == [None]
