# codexis-docs

A command-line tool that downloads the CODEXIS AI documentation from [docs.codexis.ai](https://docs.codexis.ai/), stores it locally and searches it by relevance. It needs no server: one `crawl` builds a local full-text Index, and every `search` runs against it offline.

Pages are indexed in Czech (`cs`), English (`en`) and Slovak (`sk`). Words are lemmatized, so `sdíleného účtu` finds a Page titled "Sdílený kreditový účet".

## Install

```
pipx install git+<repo-url>
```

Python 3.11 or newer is required.

## Usage

First crawl the site to build the Index. A full Crawl fetches about 300 URLs and indexes about 225 Pages:

```
codexis-docs crawl
```

Then search it:

```
codexis-docs search "sdílený kreditový účet" --lang cs
codexis-docs search "nahrávání souborů" --lang cs --limit 5
codexis-docs search "shared credit account" --lang en
codexis-docs search "zdieľaný kreditový účet" --lang sk
```

- `--lang cs|en|sk` is required. Each Search covers exactly one Language.
- `--limit N` caps the number of Results (default 10).
- The query is a list of keywords, and **every keyword must match** in some word form. There are no operators, phrases or stop words.

Each Result shows the Page's Title, its URL and a Snippet around the matched words. On a terminal, the matched words are shown in bold.

Exit codes: `0` success (also when nothing matches), `1` runtime error (no Index, Crawl aborted), `2` usage error.

## Where the Index lives

The Index is a single SQLite file at `~/.codexis-docs/index.db`. The environment variable `CODEXIS_DOCS_HOME` overrides the directory.

Each `crawl` builds a fresh Index next to the old one and swaps it in only when complete. If a documentation page can't be fetched, the Crawl aborts and the existing Index is left untouched.

## Development

```
pip install -e '.[dev]'
pytest
```

The test suite needs no network access. The crawler is tested against a fake site served by `httpx.MockTransport`, and Main text extraction against real pages saved under `tests/fixtures/pages/`.

## Design decisions

- [CONTEXT.md](CONTEXT.md): the domain vocabulary (Page, Main text, Crawl, Index, Search, …).
- [ADR-0001](docs/adr/0001-sqlite-fts5-with-python-lemmatizing-tokenizer.md): SQLite FTS5 via `apsw` with a Python lemmatizing tokenizer per Language.
- [ADR-0002](docs/adr/0002-index-docs-sections-crawl-whole-host.md): follow links across the whole host, but index only the Docs sections.
