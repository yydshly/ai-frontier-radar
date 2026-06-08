"""URL-based pattern classifier for input routing."""

import re
from urllib.parse import urlparse

from app.intake.models import IntakeDecision, PageType, RecommendedStrategy


def classify_url_by_pattern(url: str) -> IntakeDecision:
    """
    Classify a URL by its structure and path patterns.

    This is a fast, rule-based classifier that runs before any HTTP fetch.
    Checks are ordered: most specific / destructive first.

    Returns an IntakeDecision with page_type, recommended strategy,
    whether direct compilation is allowed, confidence score, and a reason.
    """
    parsed = urlparse(url)
    path = parsed.path.rstrip("/").lower()
    query = parsed.query.lower()
    lower_url = url.lower()

    # ── 1. PDF ─────────────────────────────────────────────────────
    if lower_url.endswith(".pdf"):
        return IntakeDecision(
            url=url,
            page_type=PageType.PDF,
            strategy=RecommendedStrategy.COMPILE,
            can_compile_directly=True,
            confidence=0.95,
            reason="URL ends with .pdf — PDF content is compiled directly.",
        )

    # ── 2. Feed / RSS / Atom ────────────────────────────────────────
    # Match any URL whose path ends with /feed, /rss, /atom (optionally with .xml suffix)
    # or whose full URL contains a feed-like extension
    _feed_patterns = [
        r"/feed(?:/|\.xml)?$",
        r"/rss(?:/|\.xml)?$",
        r"/atom(?:/|\.xml)?$",
        r"\.rss\.xml$",
        r"\.atom\.xml$",
        r"\.feed\.xml$",
    ]
    for pat in _feed_patterns:
        if re.search(pat, lower_url):
            return IntakeDecision(
                url=url,
                page_type=PageType.FEED,
                strategy=RecommendedStrategy.DISCOVERY_ONLY,
                can_compile_directly=False,
                confidence=0.95,
                reason="URL is a feed (RSS/Atom) — use it to discover article links, not to compile.",
            )

    # ── 3. Tag / Category / Search ──────────────────────────────────
    # These appear in either the path or the query string
    _tag_patterns = [
        r"/tag/", r"/category/", r"/topic/", r"/label/",
        r"(?:^|[?&])(tag|category|topic|search|q)=",  # query-string forms
    ]
    for pat in _tag_patterns:
        if re.search(pat, path, re.IGNORECASE) or re.search(pat, query):
            return IntakeDecision(
                url=url,
                page_type=PageType.TAG_OR_CATEGORY,
                strategy=RecommendedStrategy.DISCOVERY_ONLY,
                can_compile_directly=False,
                confidence=0.90,
                reason="URL appears to be a tag, category, or search results page — use to discover articles.",
            )

    # ── 4. Pagination ───────────────────────────────────────────────
    _page_patterns = [
        r"/page/\d+",
        r"(?:^|[?&])(page|p)=\d+",
        r"/p\d+",
    ]
    for pat in _page_patterns:
        if re.search(pat, path, re.IGNORECASE) or re.search(pat, query):
            return IntakeDecision(
                url=url,
                page_type=PageType.PAGINATION,
                strategy=RecommendedStrategy.DISCOVERY_ONLY,
                can_compile_directly=False,
                confidence=0.90,
                reason="URL contains pagination pattern — use for discovering articles, not direct compilation.",
            )

    # ── 5. Short listing / index paths ──────────────────────────────
    # Only matches bare index paths like /blog, /news — not slugs like /blog/sima-2-agent
    _short_listing = {
        "/blog", "/news", "/research", "/articles",
        "/posts", "/updates", "/discover",
    }
    if path in _short_listing:
        return IntakeDecision(
            url=url,
            page_type=PageType.LISTING,
            strategy=RecommendedStrategy.DISCOVERY_ONLY,
            can_compile_directly=False,
            confidence=0.85,
            reason="URL is a listing or index page — use to discover articles, not direct compilation.",
        )

    # ── 6. Specific known listing domains ───────────────────────────
    # DeepMind /blog/, /discover/blog/, /discover/research/ are listing pages
    # (but /blog/slug, /discover/blog/slug are articles)
    _domain = parsed.netloc.lower()
    _deepmind_listing_paths = (
        "/blog",
        "/discover/blog",
        "/discover/research",
        "/research",
    )
    if _domain in ("deepmind.google.dev", "deepmind.google.com", "deepmind.google") and (
        path.startswith("/blog") or path.startswith("/discover/") or path.startswith("/research")
    ):
        # Exact listing paths
        if path in _deepmind_listing_paths or path in (p + "/" for p in _deepmind_listing_paths):
            return IntakeDecision(
                url=url,
                page_type=PageType.LISTING,
                strategy=RecommendedStrategy.DISCOVERY_ONLY,
                can_compile_directly=False,
                confidence=0.90,
                reason="DeepMind listing page — discover articles from it, not compile directly.",
            )
        # Pagination: /blog/page/N, /discover/blog/page/N, etc.
        if re.search(r"/(blog|discover/blog|discover/research|research)/page/\d+", path):
            return IntakeDecision(
                url=url,
                page_type=PageType.PAGINATION,
                strategy=RecommendedStrategy.DISCOVERY_ONLY,
                can_compile_directly=False,
                confidence=0.95,
                reason="DeepMind pagination page — use to discover articles, not compile directly.",
            )
        # Specific article: /discover/blog/sima-2-agent, /blog/some-article
        # Already handled by slug heuristic below; allow compile for known article patterns
        if re.search(r"/(blog|discover/blog|discover/research|research)/[a-z]", path):
            # It's a deeper path — likely an article (not /blog/page/N or /discover/blog/)
            pass  # fall through to slug heuristic below

    # ── 7. Slug-like URL (probable article) ─────────────────────────
    # Heuristic: path has multiple segments or looks like a content slug
    # e.g. /blog/sima-2-agent, /news/2024/06/something
    if re.search(r"/[a-z][a-z0-9_-]+/[a-z][a-z0-9_-]", path):
        return IntakeDecision(
            url=url,
            page_type=PageType.ARTICLE,
            strategy=RecommendedStrategy.COMPILE,
            can_compile_directly=True,
            confidence=0.75,
            reason="URL structure resembles a specific article or content page.",
        )

    # ── 8. Fallback: unknown ────────────────────────────────────────
    # Allow by default; downstream handles failures
    return IntakeDecision(
        url=url,
        page_type=PageType.UNKNOWN,
        strategy=RecommendedStrategy.MANUAL_REVIEW,
        can_compile_directly=True,
        confidence=0.50,
        reason="URL type could not be determined — will attempt compilation; inspect result if it seems wrong.",
    )
