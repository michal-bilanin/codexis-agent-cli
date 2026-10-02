"""Main text extraction: Title, Language and Main text of one Page."""

from dataclasses import dataclass
from typing import cast

from selectolax.parser import HTMLParser, Node

from codexis_docs.config import LANGUAGES

TITLE_SUFFIX = " | CODEXIS AI"

# Elements that never hold Main text, removed with their content.
STRUCTURAL_TAGS = (
    "nav, header, footer, aside, script, style, noscript, template,"
    " button, svg, img, form, iframe"
)
# Blocks that are dropped when nearly all of their text is link text.
LINK_DENSE_CANDIDATES = "div, section, p, ul, ol, li, table"
LINK_DENSITY_LIMIT = 0.9
# Elements that start a new line of Main text.
LINE_TAGS = frozenset(
    "address article blockquote br caption dd details div dl dt figcaption"
    " figure h1 h2 h3 h4 h5 h6 hr li main ol p pre section summary table"
    " tbody td tfoot th thead tr ul".split()
)


@dataclass(frozen=True)
class Extracted:
    title: str
    lang: str
    main_text: str


@dataclass(frozen=True)
class Skipped:
    reason: str


def extract(html: str, url: str) -> Extracted | Skipped:
    """Return the Title, Language and Main text of the page at `url`.

    Returns Skipped with a reason when the page has no supported Language or
    no <article>/<main> root.
    """
    tree = HTMLParser(html)
    lang = _language(tree)
    if not lang:
        return Skipped("no <html lang> attribute")
    if lang not in LANGUAGES:
        return Skipped(f"unsupported language {lang!r}")
    root = _root(tree)
    if root is None:
        return Skipped("no <article> or <main> element")
    title = _title(tree, root)
    _remove_boilerplate(root)
    return Extracted(title=title, lang=lang, main_text="\n".join(_lines(root)))


def _language(tree: HTMLParser) -> str:
    html = tree.css_first("html")
    value = (html.attributes.get("lang") if html else None) or ""
    return value.split("-")[0].strip().lower()


def _root(tree: HTMLParser) -> Node | None:
    articles = tree.css("article")
    if len(articles) == 1:
        return articles[0]
    return tree.css_first("main")


def _title(tree: HTMLParser, root: Node) -> str:
    h1 = root.css_first("h1")
    if h1 is not None:
        return _collapse(h1.text())
    title = tree.css_first("title")
    text = _collapse(title.text()) if title else ""
    return text.removesuffix(TITLE_SUFFIX)


def _remove_boilerplate(root: Node) -> None:
    _remove(root.css(STRUCTURAL_TAGS))
    _remove_up_to_first_h1(root)
    _remove(
        [node for node in root.css(LINK_DENSE_CANDIDATES) if _is_link_dense(node)]
    )


def _remove_up_to_first_h1(root: Node) -> None:
    # The breadcrumb sits before the <h1>, and the <h1> itself is the Title.
    h1 = root.css_first("h1")
    if h1 is None:
        return
    preceding = []
    node = h1
    while node.parent is not None and _node_id(node) != _node_id(root):
        sibling = node.prev
        while sibling is not None:
            preceding.append(sibling)
            sibling = sibling.prev
        node = node.parent
    _remove([*preceding, h1])


def _is_link_dense(node: Node) -> bool:
    total = _length(node.text())
    if total == 0:
        return False
    if _inside_link(node):
        return True
    linked = sum(_length(a.text()) for a in node.css("a"))
    return linked >= LINK_DENSITY_LIMIT * total


def _inside_link(node: Node) -> bool:
    parent = node.parent
    while parent is not None:
        if parent.tag == "a":
            return True
        parent = parent.parent
    return False


def _length(text: str) -> int:
    # Whitespace is layout, not content, so it does not count.
    return sum(not char.isspace() for char in text)


def _remove(nodes: list[Node]) -> None:
    # Only the outermost nodes are decomposed: a descendant of a decomposed
    # node is already freed and must not be touched again.
    ids = {_node_id(node) for node in nodes}
    for node in nodes:
        if not _has_ancestor_in(node, ids):
            node.decompose()


def _has_ancestor_in(node: Node, ids: set[int]) -> bool:
    parent = node.parent
    while parent is not None:
        if _node_id(parent) in ids:
            return True
        parent = parent.parent
    return False


def _node_id(node: Node) -> int:
    # Wrappers of the same node differ, its memory address does not. The
    # selectolax stub declares mem_id as a method, but it is a property.
    return cast(int, node.mem_id)


def _lines(root: Node) -> list[str]:
    """Return the text of `root`, one line per block element."""
    lines: list[str] = []
    current: list[str] = []

    def flush() -> None:
        line = _collapse("".join(current))
        current.clear()
        if line:
            lines.append(line)

    def walk(node: Node) -> None:
        for child in node.iter(include_text=True):
            if child.tag == "-text":
                current.append(child.text_content or "")
            elif child.tag in LINE_TAGS:
                flush()
                walk(child)
                flush()
            else:
                walk(child)

    walk(root)
    flush()
    return lines


def _collapse(text: str) -> str:
    return " ".join(text.split())
