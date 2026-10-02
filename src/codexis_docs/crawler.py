"""The Crawl's walk over HOST: fetching, link following and URL rules (ADR-0002)."""

import posixpath
import time
from collections import deque
from collections.abc import Callable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from selectolax.lexbor import LexborHTMLParser

from codexis_docs.config import (
    CRAWL_CONCURRENCY,
    CRAWL_MAX_URLS,
    CRAWL_RETRIES,
    CRAWL_TIMEOUT,
    DOCS_SECTIONS,
    HOST,
    LANGUAGES,
    SEEDS,
    USER_AGENT,
)

# A Docs section may sit under a URL language prefix such as /en/guide/.
_LANG_PREFIXES = ("",) + tuple(f"/{lang}" for lang in LANGUAGES)
_ROBOTS_URL = f"https://{HOST}/robots.txt"


def make_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Return the HTTP client for a Crawl; `transport=None` uses the network."""
    return httpx.Client(
        headers={"User-Agent": USER_AGENT},
        timeout=CRAWL_TIMEOUT,
        follow_redirects=True,
        transport=transport,
    )


def in_docs_section(url: str) -> bool:
    """Tell whether `url` is on HOST under one of the DOCS_SECTIONS."""
    parts = urlsplit(url)
    if parts.hostname != HOST:
        return False
    return any(
        parts.path.startswith(prefix + section)
        for prefix in _LANG_PREFIXES
        for section in DOCS_SECTIONS
    )


def normalize_url(href: str, base: str) -> str | None:
    """Resolve `href` against `base` into the canonical form of a HOST URL.

    The result uses https, has no query or fragment, and ends with a slash
    unless its last segment has a file extension. Returns None for links to
    other hosts or other schemes, and for files other than `.html`.
    """
    parts = urlsplit(urljoin(base, href.strip()))
    if parts.scheme not in ("http", "https") or parts.hostname != HOST:
        return None
    path = parts.path or "/"
    extension = posixpath.splitext(posixpath.basename(path))[1]
    if extension:
        if extension.lower() != ".html":
            return None
    elif not path.endswith("/"):
        path += "/"
    return f"https://{HOST}{path}"


def _ignore(message: str) -> None:
    pass


class Crawler:
    """A breadth-first walk over HOST from SEEDS that yields Docs-section pages.

    4xx responses are skipped with a warning. Timeouts, connection errors and
    5xx responses are retried CRAWL_RETRIES times; after that they are a
    warning and, for Docs-section URLs, also recorded in `failures`.
    """

    def __init__(
        self,
        client: httpx.Client,
        *,
        on_warning: Callable[[str], None] = _ignore,
        on_progress: Callable[[int, int], None] | None = None,
        backoff: float = 0.5,
        max_urls: int = CRAWL_MAX_URLS,
    ) -> None:
        self.warnings: list[str] = []
        self.failures: list[str] = []
        self.fetched = 0
        self._client = client
        self._on_warning = on_warning
        self._on_progress = on_progress
        self._backoff = backoff
        self._max_urls = max_urls
        self._robots = RobotFileParser()
        self._queue: deque[str] = deque()
        self._seen: set[str] = set()
        self._finals: set[str] = set()

    def pages(self) -> Iterator[tuple[str, str]]:
        """Yield (final_url, html) for every Docs-section HTML page found."""
        self._robots = self._read_robots()
        for seed in SEEDS:
            self._enqueue(seed)
        pool = ThreadPoolExecutor(CRAWL_CONCURRENCY)
        in_flight: dict[Future[httpx.Response | str], str] = {}
        submitted = 0
        capped = False
        try:
            while in_flight or (self._queue and not capped):
                while self._queue and len(in_flight) < CRAWL_CONCURRENCY:
                    if submitted >= self._max_urls:
                        capped = True
                        self._warn(
                            f"Stopped after {submitted} URLs: "
                            "the safety cap was reached"
                        )
                        break
                    url = self._queue.popleft()
                    if url in self._finals:
                        continue  # already reached through a redirect
                    in_flight[pool.submit(self._get, url)] = url
                    submitted += 1
                if not in_flight:
                    continue
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for future in done:
                    url = in_flight.pop(future)
                    self.fetched += 1
                    page = self._handle(url, future.result())
                    if self._on_progress is not None:
                        self._on_progress(
                            self.fetched, len(self._queue) + len(in_flight)
                        )
                    if page is not None:
                        yield page
        finally:
            pool.shutdown(cancel_futures=True)

    def _read_robots(self) -> RobotFileParser:
        # An unfetchable robots.txt, even a 401/403 that urllib.robotparser
        # would treat as "disallow all", allows everything: an empty file.
        result = self._get(_ROBOTS_URL)
        lines: list[str] = []
        if isinstance(result, str):
            self._warn(f"Could not fetch {_ROBOTS_URL} ({result}), allowing all")
        elif result.is_success:
            lines = result.text.splitlines()
        robots = RobotFileParser(_ROBOTS_URL)
        robots.parse(lines)
        return robots

    def _enqueue(self, url: str) -> None:
        if url in self._seen:
            return
        self._seen.add(url)
        if self._robots.can_fetch(USER_AGENT, url):
            self._queue.append(url)

    def _get(self, url: str) -> httpx.Response | str:
        """Fetch `url` with retries; return the response or a failure reason."""
        reason = ""
        for attempt in range(CRAWL_RETRIES + 1):
            if attempt:
                time.sleep(self._backoff * 2 ** (attempt - 1))
            try:
                response = self._client.get(url)
            except httpx.TransportError as exc:
                reason = f"{type(exc).__name__}: {exc}"
                continue
            except httpx.RequestError as exc:
                # Such as too many redirects, which a retry would not fix.
                return f"{type(exc).__name__}: {exc}"
            if response.status_code < 500:
                return response
            reason = f"HTTP {response.status_code}"
        return reason

    def _handle(self, url: str, result: httpx.Response | str) -> tuple[str, str] | None:
        """Record one fetch, queue its links and return it if it is a Page."""
        if isinstance(result, str):
            self._warn(f"Failed to fetch {url}: {result}")
            if in_docs_section(url):
                self.failures.append(url)
            return None
        final = normalize_url(str(result.url), url)
        if final is None or final in self._finals:
            return None  # redirected off HOST, to a file, or to a known URL
        self._finals.add(final)
        self._seen.add(final)
        if not result.is_success:
            self._warn(f"Skipped {url}: HTTP {result.status_code}")
            return None
        content_type = result.headers.get("Content-Type", "")
        if content_type.split(";")[0].strip().lower() != "text/html":
            return None
        html = result.text
        for link in LexborHTMLParser(html).css("a[href]"):
            href = link.attributes.get("href")
            if href:
                target = normalize_url(href, str(result.url))
                if target is not None:
                    self._enqueue(target)
        return (final, html) if in_docs_section(final) else None

    def _warn(self, message: str) -> None:
        self.warnings.append(message)
        self._on_warning(message)
