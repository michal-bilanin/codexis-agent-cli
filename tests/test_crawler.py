import httpx
import pytest

from codexis_docs.config import CRAWL_RETRIES, CRAWL_TIMEOUT, USER_AGENT
from codexis_docs.crawler import (
    Crawler,
    in_docs_section,
    make_client,
    normalize_url,
)

BASE = "https://docs.codexis.ai/funkce/"


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("/guide/a", "https://docs.codexis.ai/guide/a/"),
        ("../guide/a/", "https://docs.codexis.ai/guide/a/"),
        ("sub", "https://docs.codexis.ai/funkce/sub/"),
        ("http://docs.codexis.ai/guide/a/", "https://docs.codexis.ai/guide/a/"),
        ("/guide/a/#install", "https://docs.codexis.ai/guide/a/"),
        ("/guide/a/?page=2", "https://docs.codexis.ai/guide/a/"),
        ("#top", "https://docs.codexis.ai/funkce/"),
        ("/old/page.html", "https://docs.codexis.ai/old/page.html"),
        ("https://DOCS.codexis.ai", "https://docs.codexis.ai/"),
    ],
)
def test_normalize_url(href, expected):
    assert normalize_url(href, BASE) == expected


@pytest.mark.parametrize(
    "href",
    [
        "https://example.com/guide/a/",
        "https://www.codexis.ai/",
        "mailto:info@codexis.ai",
        "javascript:void(0)",
        "/content-assets/api.yaml",
        "/images/logo.PNG",
        "/manual.pdf?download=1",
    ],
)
def test_normalize_url_rejects_other_hosts_and_non_html_files(href):
    assert normalize_url(href, BASE) is None


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://docs.codexis.ai/guide/", True),
        ("https://docs.codexis.ai/guide/a/", True),
        ("https://docs.codexis.ai/codexis-ai-2-0/novinky/", True),
        ("https://docs.codexis.ai/en/guide/a/", True),
        ("https://docs.codexis.ai/sk/codexis-ai-2-0/", True),
        ("https://docs.codexis.ai/", False),
        ("https://docs.codexis.ai/en/", False),
        ("https://docs.codexis.ai/funkce/", False),
        ("https://docs.codexis.ai/guidelines/", False),
        ("https://docs.codexis.ai/de/guide/a/", False),
        ("https://docs.codexis.ai/funkce/guide/", False),
        ("https://example.com/guide/a/", False),
    ],
)
def test_in_docs_section(url, expected):
    assert in_docs_section(url) is expected


ROBOTS = "User-agent: *\nDisallow: /guide/private/\n"


def html(*hrefs: str) -> str:
    links = "".join(f'<a href="{href}">link</a>' for href in hrefs)
    return f"<html><body>{links}</body></html>"


class FakeSite:
    """A small docs.codexis.ai served through httpx.MockTransport."""

    def __init__(self, robots: httpx.Response | None = None) -> None:
        self.requests: list[httpx.Request] = []
        self.robots = robots or httpx.Response(200, text=ROBOTS)
        self.flaky_calls = 0
        self.pages: dict[str, str] = {
            "/": html("/funkce/", "/guide/", "/kontakt/", "/pro-koho/"),
            "/en/": html("/en/guide/a/", "/", "/en/stary-navod/"),
            "/sk/": html("/sk/guide/a/"),
            "/funkce/": html(
                "/guide/hidden/",
                "https://example.com/guide/other/",
                "/guide/a#install",
                "/guide/a?tab=2",
                "/guide/a",
                "/guide/moved/",
                "/images/logo.png",
                "/content-assets/api.yaml",
                "/guide/private/secret/",
                "/guide/flaky/",
                "/guide/broken/",
                "/guide/manual/",
            ),
            "/guide/hidden/": html("/funkce/"),
            "/guide/a/": html("/guide/a/", "/guide/moved/"),
            "/guide/flaky/": html(),
            "/en/guide/a/": html("/guide/a/"),
            "/en/guide/b/": html("/en/guide/c/"),
            "/en/guide/c/": html("/en/guide/b/"),
            "/sk/guide/a/": html(),
        }

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.host == "docs.codexis.ai"
        path = request.url.path
        if path == "/robots.txt":
            return self.robots
        if path == "/guide/":
            return httpx.Response(403)
        if path == "/guide/moved/":
            return httpx.Response(301, headers={"Location": "/guide/a/"})
        if path == "/en/stary-navod/":
            return httpx.Response(308, headers={"Location": "/en/guide/b"})
        if path == "/en/guide/b":
            return httpx.Response(301, headers={"Location": "/en/guide/b/"})
        if path == "/guide/flaky/":
            self.flaky_calls += 1
            if self.flaky_calls == 1:
                return httpx.Response(502)
        if path in ("/guide/broken/", "/pro-koho/"):
            return httpx.Response(503)
        if path == "/guide/manual/":
            return httpx.Response(
                200, content=b"%PDF-1.4", headers={"Content-Type": "application/pdf"}
            )
        if path in self.pages:
            return httpx.Response(
                200,
                text=self.pages[path],
                headers={"Content-Type": "text/html; charset=utf-8"},
            )
        return httpx.Response(404)

    def requested(self, path: str) -> int:
        return sum(1 for request in self.requests if request.url.path == path)


def crawl(site: FakeSite, **kwargs) -> tuple[Crawler, list[tuple[str, str]]]:
    client = make_client(httpx.MockTransport(site.handler))
    crawler = Crawler(client, backoff=0, **kwargs)
    return crawler, list(crawler.pages())


def url(path: str) -> str:
    return f"https://docs.codexis.ai{path}"


def test_yields_only_docs_section_pages_once():
    _, pages = crawl(FakeSite())
    urls = [final_url for final_url, _ in pages]
    assert len(urls) == len(set(urls))
    assert set(urls) == {
        url("/guide/hidden/"),
        url("/guide/a/"),
        url("/guide/flaky/"),
        url("/en/guide/a/"),
        url("/en/guide/b/"),
        url("/en/guide/c/"),
        url("/sk/guide/a/"),
    }


def test_yields_the_html_of_each_page():
    site = FakeSite()
    _, pages = crawl(site)
    assert dict(pages)[url("/guide/hidden/")] == site.pages["/guide/hidden/"]


def test_marketing_pages_are_fetched_for_links():
    site = FakeSite()
    crawl(site)
    assert site.requested("/") == 1
    assert site.requested("/funkce/") == 1


def test_skipped_links_are_not_fetched():
    site = FakeSite()
    crawl(site)
    paths = [request.url.path for request in site.requests]
    assert "/images/logo.png" not in paths
    assert "/content-assets/api.yaml" not in paths
    assert "/guide/private/secret/" not in paths
    assert "/guide/a" not in paths
    assert all(not request.url.query for request in site.requests)


def test_each_url_is_requested_once():
    site = FakeSite()
    crawl(site)
    assert site.requested("/") == 1
    assert site.requested("/funkce/") == 1
    assert site.requested("/guide/moved/") == 1
    assert site.requested("/en/guide/a/") == 1


def test_redirect_target_is_not_fetched_again():
    site = FakeSite()
    _, pages = crawl(site)
    # /en/guide/b/ is reached through /en/stary-navod/ and later linked from
    # /en/guide/c/, which is only reachable from /en/guide/b/ itself.
    assert site.requested("/en/guide/b/") == 1
    assert [u for u, _ in pages].count(url("/en/guide/b/")) == 1


def test_non_html_responses_are_skipped_silently():
    site = FakeSite()
    crawler, pages = crawl(site)
    assert site.requested("/guide/manual/") == 1
    assert url("/guide/manual/") not in dict(pages)
    assert not any("/guide/manual/" in w for w in crawler.warnings)


def test_client_errors_are_warnings():
    crawler, _ = crawl(FakeSite())
    assert url("/guide/") not in crawler.failures
    assert url("/kontakt/") not in crawler.failures
    assert any("/guide/" in w and "403" in w for w in crawler.warnings)
    assert any("/kontakt/" in w and "404" in w for w in crawler.warnings)


def test_server_error_then_success_is_retried():
    site = FakeSite()
    crawler, pages = crawl(site)
    assert site.requested("/guide/flaky/") == 2
    assert url("/guide/flaky/") in dict(pages)
    assert not any("/guide/flaky/" in w for w in crawler.warnings)


def test_persistent_server_error_in_docs_section_is_a_failure():
    site = FakeSite()
    crawler, _ = crawl(site)
    assert site.requested("/guide/broken/") == 1 + CRAWL_RETRIES
    assert crawler.failures == [url("/guide/broken/")]


def test_persistent_server_error_outside_docs_sections_is_a_warning():
    site = FakeSite()
    crawler, _ = crawl(site)
    assert site.requested("/pro-koho/") == 1 + CRAWL_RETRIES
    assert url("/pro-koho/") not in crawler.failures
    assert any("/pro-koho/" in w and "503" in w for w in crawler.warnings)


def test_requests_carry_the_user_agent():
    site = FakeSite()
    crawl(site)
    assert site.requests
    assert all(r.headers["User-Agent"] == USER_AGENT for r in site.requests)


def test_robots_disallow_is_obeyed():
    site = FakeSite()
    crawl(site)
    assert site.requested("/robots.txt") == 1
    assert site.requested("/guide/private/secret/") == 0


@pytest.mark.parametrize("status", [404, 403, 503])
def test_unfetchable_robots_allows_everything(status):
    site = FakeSite(robots=httpx.Response(status))
    crawler, _ = crawl(site)
    assert site.requested("/guide/private/secret/") == 1
    assert crawler.failures == [url("/guide/broken/")]


def test_robots_connection_error_allows_everything():
    site = FakeSite()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            raise httpx.ConnectError("refused", request=request)
        return site.handler(request)

    crawler = Crawler(make_client(httpx.MockTransport(handler)), backoff=0)
    list(crawler.pages())
    assert site.requested("/guide/private/secret/") == 1
    assert any("robots.txt" in w for w in crawler.warnings)


@pytest.mark.parametrize(
    "error", [httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError]
)
def test_transport_errors_are_retried(error):
    site = FakeSite()
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        if request.url.path == "/sk/guide/a/":
            calls += 1
            if calls <= CRAWL_RETRIES:
                raise error("boom", request=request)
        return site.handler(request)

    crawler = Crawler(make_client(httpx.MockTransport(handler)), backoff=0)
    pages = dict(crawler.pages())
    assert calls == 1 + CRAWL_RETRIES
    assert url("/sk/guide/a/") in pages


def test_persistent_transport_error_in_docs_section_is_a_failure():
    site = FakeSite()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/sk/guide/a/":
            raise httpx.ReadTimeout("slow", request=request)
        return site.handler(request)

    crawler = Crawler(make_client(httpx.MockTransport(handler)), backoff=0)
    list(crawler.pages())
    assert url("/sk/guide/a/") in crawler.failures
    assert any("/sk/guide/a/" in w and "ReadTimeout" in w for w in crawler.warnings)


def test_safety_cap_stops_the_walk_with_a_warning():
    site = FakeSite()
    crawler, _ = crawl(site, max_urls=5)
    assert crawler.fetched == 5
    # The 3 seeds plus 2 links of the second BFS level; the third is not reached.
    assert site.requested("/guide/hidden/") == 0
    assert any("cap" in w for w in crawler.warnings)


def test_no_cap_warning_when_the_walk_fits():
    crawler, _ = crawl(FakeSite())
    assert not any("cap" in w for w in crawler.warnings)


def test_callbacks_receive_warnings_and_progress() -> None:
    warnings: list[str] = []
    progress: list[tuple[int, int]] = []
    crawler, _ = crawl(
        FakeSite(),
        on_warning=warnings.append,
        on_progress=lambda fetched, queued: progress.append((fetched, queued)),
    )
    assert warnings == crawler.warnings
    assert [fetched for fetched, _ in progress] == list(range(1, crawler.fetched + 1))
    assert progress[-1] == (crawler.fetched, 0)


def test_make_client_settings():
    with make_client() as client:
        assert client.headers["User-Agent"] == USER_AGENT
        assert client.timeout == httpx.Timeout(CRAWL_TIMEOUT)
        assert client.follow_redirects is True
