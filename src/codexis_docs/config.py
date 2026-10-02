"""Configuration constants and the Index location."""

import os
from pathlib import Path

from codexis_docs import __version__

LANGUAGES = ("cs", "en", "sk")

HOST = "docs.codexis.ai"
SEEDS = (
    f"https://{HOST}/",
    f"https://{HOST}/en/",
    f"https://{HOST}/sk/",
)
DOCS_SECTIONS = ("/guide/", "/codexis-ai-2-0/")

# Placeholder until the repository has a public URL.
REPO_URL = "https://example.invalid/codexis-docs"

CRAWL_CONCURRENCY = 4
CRAWL_TIMEOUT = 10.0
CRAWL_RETRIES = 2
CRAWL_MAX_URLS = 5000
USER_AGENT = f"codexis-docs/{__version__} (+{REPO_URL})"

HOME_ENV_VAR = "CODEXIS_DOCS_HOME"


def index_path() -> Path:
    """Return the path of the Index file, honouring CODEXIS_DOCS_HOME."""
    home = os.environ.get(HOME_ENV_VAR)
    base = Path(home) if home else Path.home() / ".codexis-docs"
    return base / "index.db"
