"""Real pages from docs.codexis.ai, saved once under tests/fixtures/pages/.

A fixture file is named after its URL path, with `/` replaced by `--`.
"""

from pathlib import Path

PAGES_DIR = Path(__file__).parent / "fixtures" / "pages"

BASE_URL = "https://docs.codexis.ai"

FIXTURE_URLS: dict[str, str] = {
    "guide--kredity-a-cenik--sdilene-ucty.html": (
        f"{BASE_URL}/guide/kredity-a-cenik/sdilene-ucty/"
    ),
    "en--guide--kredity-a-cenik--sdilene-ucty.html": (
        f"{BASE_URL}/en/guide/kredity-a-cenik/sdilene-ucty/"
    ),
    "sk--guide--kredity-a-cenik--sdilene-ucty.html": (
        f"{BASE_URL}/sk/guide/kredity-a-cenik/sdilene-ucty/"
    ),
    "guide--nahravani-vlastnich-souboru.html": (
        f"{BASE_URL}/guide/nahravani-vlastnich-souboru/"
    ),
    "guide--rychly-start.html": f"{BASE_URL}/guide/rychly-start/",
    "guide--faq.html": f"{BASE_URL}/guide/faq/",
    "codexis-ai-2-0--manual--agenti.html": f"{BASE_URL}/codexis-ai-2-0/manual/agenti/",
    "codexis-ai-2-0--manual--projekty.html": (
        f"{BASE_URL}/codexis-ai-2-0/manual/projekty/"
    ),
    "codexis-ai-2-0--slovnik-pojmu.html": f"{BASE_URL}/codexis-ai-2-0/slovnik-pojmu/",
    "codexis-ai-2-0--integrace.html": f"{BASE_URL}/codexis-ai-2-0/integrace/",
    # A marketing page outside the Docs sections: it has <main> but no <article>.
    "funkce.html": f"{BASE_URL}/funkce/",
}


def load(name: str) -> str:
    """Return the HTML of the fixture file `name`."""
    return (PAGES_DIR / name).read_text(encoding="utf-8")
