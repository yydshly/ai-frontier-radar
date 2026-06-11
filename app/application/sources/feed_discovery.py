"""Feed auto-discovery (S5).

Finds RSS / Atom / JSON-feed links advertised in an HTML page's ``<head>`` via
``<link rel="alternate" type="application/rss+xml" ...>``. This is the basis for
suggesting that an ``html_index`` source actually has a feed and could be
upgraded to the more reliable ``rss`` strategy.

``discover_feed_links`` is a PURE function — it parses already-fetched HTML and
does no network I/O, so it is fully unit-testable offline. Network fetching and
any "suggest upgrade" reporting live in the read-only CLI
(``scripts/discover_source_feeds.py``); nothing here writes config or the DB.
"""
from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin

# Feed MIME types we consider a discoverable feed.
_FEED_TYPES = (
    "application/rss+xml",
    "application/atom+xml",
    "application/feed+json",
    "application/json",
)


@dataclass(frozen=True)
class DiscoveredFeed:
    url: str
    type: str
    title: str


class _LinkFeedParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.feeds: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "link":
            return
        d = {(k or "").lower(): (v or "") for k, v in attrs}
        rel = d.get("rel", "").lower()
        typ = d.get("type", "").lower()
        href = d.get("href", "").strip()
        if "alternate" in rel and href and any(t in typ for t in _FEED_TYPES):
            self.feeds.append((href, typ, d.get("title", "").strip()))


def discover_feed_links(html: str | None, base_url: str | None = None) -> list[DiscoveredFeed]:
    """Parse feed <link rel=alternate> entries from HTML. Pure / no network.

    ``base_url`` is used to resolve relative hrefs to absolute URLs. Results are
    de-duplicated by resolved URL, preserving document order.
    """
    parser = _LinkFeedParser()
    try:
        parser.feed(html or "")
    except Exception:
        # Malformed HTML must never raise — return whatever was parsed so far.
        pass

    out: list[DiscoveredFeed] = []
    seen: set[str] = set()
    for href, typ, title in parser.feeds:
        url = urljoin(base_url, href) if base_url else href
        if url and url not in seen:
            seen.add(url)
            out.append(DiscoveredFeed(url=url, type=typ, title=title))
    return out
