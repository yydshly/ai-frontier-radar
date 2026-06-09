"""HTML Index Source probing — discovers article links from index pages.

Does NOT fetch article body, does NOT call LLM.
"""
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urldefrag, parse_qs, urlunparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import Source, SourceItem, FetchRun
from app.sources.quality import classify_source_item_url

# Extensions to skip (static assets)
SKIP_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".ico", ".zip", ".pdf", ".doc", ".docx",
}

# Path segments to skip (obvious non-article pages)
SKIP_PATH_SEGMENTS = {
    "about", "contact", "careers", "jobs", "privacy",
    "terms", "login", "signup", "sign-up", "pricing", "team",
    "events", "docs", "api", "shop", "store", "faq", "support",
}

# Path segments that suggest article/blog content
ARTICLE_PATH_SEGMENTS = {
    "blog", "news", "research", "articles", "posts", "post",
    "paper", "papers", "report", "reports", "announcements",
    "announcement", "updates", "update", "insights", "insight",
}

# Single-level paths that are index/listing pages (not article pages)
# e.g., /blog, /news, /research — but NOT /blog/slug, /news/slug
LISTING_PAGE_PATHS = {
    "blog", "news", "research", "articles", "posts",
    "announcements", "updates", "reports",
}

# Query parameters that indicate pagination, filtering, or listing pages
LISTING_QUERY_PARAMS = {
    "p", "page", "paged", "offset", "start",
    "sort", "filter",
    "tag", "tags", "category", "search",
    "q", "author", "topic",
}

# Weak/CTA titles that should NOT be used directly as SourceItem.title.
# When a link text matches this set, we fall back to the URL slug.
WEAK_TITLES = {
    "FEATURED",
    "Learn More",
    "Read More",
    "More",
    "View",
    "Explore",
    "See More",
    "Continue Reading",
    "Details",
}

# Regex for 4-digit year in path
YEAR_PATTERN = re.compile(r"/\d{4}/|" r"-\d{4}/|" r"/\d{4}$")


def _is_weak_title(title: str) -> bool:
    """Return True if title is a weak/CTA string that should not be used directly.

    An empty or whitespace-only string is also considered weak.
    """
    if not title or not title.strip():
        return True
    return title.strip() in WEAK_TITLES


def _make_url_slug_fallback(url: str) -> str:
    """Extract a human-readable fallback title from a URL's last path segment.

    Args:
        url: Absolute URL to extract slug from.

    Returns:
        Cleaned title derived from the URL's last path segment,
        or empty string if no usable segment exists.
    """
    parsed = urlparse(url)
    path_segments = [s for s in parsed.path.split("/") if s]
    if path_segments:
        slug = path_segments[-1]
        # Common URL slug separators → spaces
        slug = slug.replace("-", " ").replace("_", " ").strip()
        return slug
    return ""


def _normalize_candidate_url(url: str) -> str:
    """Normalize a candidate URL by removing fragments and tracking parameters.

    Args:
        url: Absolute URL to normalize.

    Returns:
        Normalized URL string.
    """
    # Remove fragment
    url, _ = urldefrag(url)

    parsed = urlparse(url)

    # Remove tracking/query parameters that don't affect content identity
    tracking_params = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                       "ref", "source", "fbclid", "gclid", "_ga"}

    # Parse query string
    qs = parse_qs(parsed.query, keep_blank_values=True)

    # Filter out tracking params
    filtered_qs = {k: v for k, v in qs.items() if k not in tracking_params}

    # Reconstruct URL without tracking params
    # Keep only params that affect content (LISTING_QUERY_PARAMS)
    content_qs = {k: v for k, v in filtered_qs.items() if k in LISTING_QUERY_PARAMS}

    new_query = "&".join(f"{k}={v[0]}" for k, v in content_qs.items())

    normalized = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        "",  # no fragment
    ))

    return normalized


def _has_pagination_or_listing_query(url: str) -> bool:
    """Check if URL has pagination, filter, or listing-related query parameters.

    Args:
        url: URL to check.

    Returns:
        True if URL contains listing/pagination query parameters.
    """
    parsed = urlparse(url)
    qs = parse_qs(parsed.query, keep_blank_values=True)

    for param in qs:
        if param.lower() in LISTING_QUERY_PARAMS:
            return True

    return False


def _is_index_or_listing_url(url: str, source_homepage_url: str) -> bool:
    """Determine if URL is an index page, listing page, or pagination page.

    A URL is considered an index/listing URL if:
    - Its path is exactly a single-level listing path like /blog, /news
      (not /blog/slug which is an article)
    - OR it has pagination/filtering query params

    Args:
        url: Absolute URL to check.
        source_homepage_url: Homepage URL of the source (for path comparison).

    Returns:
        True if URL is an index/listing/pagination page (should be filtered out).
    """
    parsed = urlparse(url)
    source_parsed = urlparse(source_homepage_url)

    # Only apply same-netloc check here; caller already ensures this
    if parsed.netloc != source_parsed.netloc:
        return False

    path = parsed.path.lower().rstrip("/")

    # Empty path or just "/" is not a listing page (it's homepage)
    if not path or path == "/":
        return False

    path_segments = [seg for seg in path.split("/") if seg]

    # If path has only ONE segment and that segment is in LISTING_PAGE_PATHS,
    # it's a listing/index page (e.g., /blog, /news, /research)
    if len(path_segments) == 1 and path_segments[0] in LISTING_PAGE_PATHS:
        return True

    # If path is exactly a listing path with no trailing segment
    if path in LISTING_PAGE_PATHS:
        return True

    # If URL has pagination/listing query params, it's a listing page
    if _has_pagination_or_listing_query(url):
        return True

    return False


def _is_probable_article_url(url: str, source_homepage_url: str) -> bool:
    """Filter URL to decide if it looks like a probable article/research page.

    Args:
        url: Absolute URL to evaluate (should already be normalized).
        source_homepage_url: Homepage URL of the source (used for same-domain check).

    Returns:
        True if the URL looks like an article page worth tracking.
    """
    parsed = urlparse(url)

    # Skip different domains
    source_parsed = urlparse(source_homepage_url)
    if parsed.netloc != source_parsed.netloc:
        return False

    path = parsed.path.lower()

    # Skip empty paths or just "/"
    if not path or path == "/":
        return False

    # Skip static asset extensions
    if any(path.endswith(ext) for ext in SKIP_EXTENSIONS):
        return False

    # Skip obvious non-article path segments
    path_segments = [seg for seg in path.split("/") if seg]
    for seg in path_segments:
        if seg in SKIP_PATH_SEGMENTS:
            return False

    # Skip index/listing pages (list page paths without a trailing article slug)
    # This must come after basic path checks but before article segment checks
    if _is_index_or_listing_url(url, source_homepage_url):
        return False

    # Include if it contains article-like path segments
    for seg in path_segments:
        if seg in ARTICLE_PATH_SEGMENTS:
            return True

    # Include if path contains a 4-digit year (e.g., /2025/ or /2024/news)
    if YEAR_PATTERN.search(path):
        return True

    # Include if path has 2+ segments (e.g., /blog/post-title)
    if len(path_segments) >= 2:
        return True

    return False


def probe_html_index_source(
    db: Session, source: Source, timeout_seconds: int = 20
) -> dict:
    """Probe a single HTML index source and discover article links.

    Args:
        db: SQLAlchemy session.
        source: Source ORM object with homepage_url set.
        timeout_seconds: HTTP request timeout.

    Returns:
        dict with keys: source_key, items_found, items_new, items_updated,
                        items_failed, error_message
    """
    result = {
        "source_key": source.source_key,
        "items_found": 0,
        "items_new": 0,
        "items_updated": 0,
        "items_failed": 0,
        "error_message": None,
        "error_kind": None,
    }

    # Validate homepage_url
    if not source.homepage_url:
        result["error_message"] = "homepage_url is not set"
        result["error_kind"] = "missing_homepage_url"
        return result

    # Build request headers
    headers = {
        "User-Agent": "AI-Frontier-Radar/0.7 (+https://github.com/yydshly/ai-frontier-radar)"
    }

    # Fetch homepage
    try:
        response = httpx.get(
            source.homepage_url,
            timeout=timeout_seconds,
            follow_redirects=True,
            headers=headers,
        )
        response.raise_for_status()
    except httpx.TimeoutException:
        result["error_message"] = f"Timeout fetching homepage after {timeout_seconds}s"
        result["error_kind"] = "timeout"
        return result
    except httpx.HTTPStatusError as e:
        result["error_message"] = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        result["error_kind"] = "http_error"
        return result
    except Exception as e:
        result["error_message"] = f"Request failed: {e}"
        result["error_kind"] = "request_failed"
        return result

    # Parse HTML
    try:
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        result["error_message"] = f"Failed to parse HTML: {e}"
        result["error_kind"] = "parse_failed"
        return result

    # Find all <a> tags with href
    candidates = []
    for a_tag in soup.find_all("a", href=True):
        href = a_tag.get("href", "").strip()

        # Skip empty, mailto, javascript, tel
        if not href or href.startswith(("mailto:", "javascript:", "tel:", "#")):
            continue

        # Join with homepage to get absolute URL and defrag
        absolute_url, _ = urldefrag(urljoin(source.homepage_url, href))
        if not absolute_url:
            continue

        # Normalize URL: remove fragments and tracking params
        normalized_url = _normalize_candidate_url(absolute_url)

        # Filter using heuristic — skip index/listing/pagination URLs
        if not _is_probable_article_url(normalized_url, source.homepage_url):
            continue

        # Apply content quality classification
        classification = classify_source_item_url(
            source.source_key, normalized_url, source.homepage_url
        )
        if classification["suspected_listing"]:
            continue
        if classification["suspected_off_topic"]:
            # Log off-topic URLs for debugging (but don't store them)
            continue

        # Get link text
        link_text = a_tag.get_text(strip=True)

        # Determine title and title_source:
        # - Weak link_text → use URL slug fallback
        # - Good link_text → use link_text directly
        url_slug = _make_url_slug_fallback(absolute_url)
        if _is_weak_title(link_text):
            if url_slug:
                title = url_slug
                title_source = "url_slug"
            else:
                title = absolute_url
                title_source = "url"
        else:
            title = link_text
            title_source = "link_text"

        candidates.append({
            "url": normalized_url,
            "title": title,
            "link_text": link_text,
            "title_source": title_source,
        })

        # Cap at 50 candidates to avoid noise
        if len(candidates) >= 50:
            break

    # If no candidates found, return partial failure
    if not candidates:
        result["error_message"] = "No candidate article links found"
        result["error_kind"] = "no_candidates"
        return result

    # Deduplicate by URL before processing
    seen_urls: set[str] = set()
    deduped_candidates = []
    for candidate in candidates:
        if candidate["url"] in seen_urls:
            continue
        seen_urls.add(candidate["url"])
        deduped_candidates.append(candidate)

    # Process each candidate
    for candidate in deduped_candidates:
        result["items_found"] += 1

        # Check if item already exists
        existing = (
            db.query(SourceItem)
            .filter(SourceItem.source_id == source.id, SourceItem.url == candidate["url"])
            .first()
        )

        raw_metadata = {
            "link_text": candidate["link_text"],
            "title_source": candidate["title_source"],
            "source_homepage_url": source.homepage_url,
            "discovered_by": "html_index",
        }

        if existing is None:
            # Create new SourceItem
            item = SourceItem(
                source_id=source.id,
                source_key=source.source_key,
                url=candidate["url"],
                canonical_url=candidate["url"],
                title=candidate["title"],
                author=None,
                published_at=None,
                raw_metadata_json=json.dumps(raw_metadata, ensure_ascii=False),
                status="discovered",
                last_seen_at=datetime.utcnow(),
            )
            db.add(item)
            result["items_new"] += 1
        else:
            # Update existing item — protect existing good titles from being
            # overwritten by newly discovered weak titles.
            should_update_title = True
            if existing.title and not _is_weak_title(existing.title):
                # Existing has a good title; keep it unless new title is also good
                if _is_weak_title(candidate["title"]):
                    should_update_title = False

            if should_update_title:
                existing.title = candidate["title"]

            existing.raw_metadata_json = json.dumps(raw_metadata, ensure_ascii=False)
            existing.last_seen_at = datetime.utcnow()
            result["items_updated"] += 1

    db.commit()
    return result


def run_html_index_probe_for_source(db: Session, source: Source, timeout_seconds: int = 20) -> FetchRun:
    """Run HTML index probe for a single source and record a FetchRun.

    Args:
        db: SQLAlchemy session.
        source: Source ORM object.
        timeout_seconds: HTTP request timeout.

    Returns:
        FetchRun ORM object (committed to DB).
    """
    # Create FetchRun in running state
    fetch_run = FetchRun(
        source_id=source.id,
        source_key=source.source_key,
        run_type="manual",
        status="running",
        started_at=datetime.utcnow(),
    )
    db.add(fetch_run)
    db.commit()
    db.refresh(fetch_run)

    try:
        probe_result = probe_html_index_source(db, source, timeout_seconds=timeout_seconds)

        # Update fetch run fields
        fetch_run.items_found = probe_result["items_found"]
        fetch_run.items_new = probe_result["items_new"]
        fetch_run.items_updated = probe_result["items_updated"]
        fetch_run.items_failed = probe_result["items_failed"]
        fetch_run.finished_at = datetime.utcnow()

        items_found = probe_result["items_found"]
        items_failed = probe_result["items_failed"]
        error_message = probe_result["error_message"]
        error_kind = probe_result.get("error_kind")

        if error_kind == "no_candidates":
            # Page accessible but no candidate links found — partial failure
            fetch_run.status = "partial_failed"
            fetch_run.error_message = error_message

            source.last_checked_at = datetime.utcnow()
            source.last_error_message = error_message
            # Do NOT update last_success_at — no items were actually discovered
        elif error_message:
            # Page fetch/parse failure — full failure
            fetch_run.status = "failed"
            fetch_run.error_message = error_message

            source.last_checked_at = datetime.utcnow()
            source.last_error_message = error_message
            # Do NOT update last_success_at
        elif items_failed > 0 and items_found > items_failed:
            # Some items failed
            fetch_run.status = "partial_failed"
            fetch_run.error_message = f"{items_failed} item(s) failed during HTML parsing"

            source.last_checked_at = datetime.utcnow()
            source.last_success_at = datetime.utcnow()
            source.last_error_message = fetch_run.error_message
        elif items_failed > 0 and items_found == items_failed:
            # All items failed
            fetch_run.status = "failed"
            fetch_run.error_message = "All HTML entries failed during parsing"

            source.last_checked_at = datetime.utcnow()
            source.last_error_message = fetch_run.error_message
        else:
            # All succeeded
            fetch_run.status = "success"
            fetch_run.error_message = None

            source.last_checked_at = datetime.utcnow()
            source.last_success_at = datetime.utcnow()
            source.last_error_message = None

        db.commit()
        db.refresh(fetch_run)
        return fetch_run

    except Exception as e:
        db.rollback()

        fetch_run.status = "failed"
        fetch_run.error_message = str(e)
        fetch_run.finished_at = datetime.utcnow()

        source.last_checked_at = datetime.utcnow()
        source.last_error_message = str(e)

        db.commit()
        db.refresh(fetch_run)
        return fetch_run


def run_html_index_probe_for_enabled_sources(
    db: Session,
    source_key: str | None = None,
    limit_sources: int | None = None,
    timeout_seconds: int = 20,
) -> dict:
    """Run HTML index probe for enabled HTML index sources.

    Args:
        db: SQLAlchemy session.
        source_key: If set, only probe this specific source_key.
        limit_sources: If set, probe at most this many sources.
        timeout_seconds: HTTP request timeout.

    Returns:
        dict with aggregate statistics across all HTML index sources.
    """
    query = db.query(Source).filter(
        Source.enabled == True, Source.fetch_strategy == "html_index"
    )

    if source_key is not None:
        query = query.filter(Source.source_key == source_key)

    enabled_html_sources = query.all()

    if limit_sources is not None:
        enabled_html_sources = enabled_html_sources[:limit_sources]

    total = len(enabled_html_sources)
    success_count = 0
    failed_count = 0

    items_found_total = 0
    items_new_total = 0
    items_updated_total = 0
    items_failed_total = 0

    for source in enabled_html_sources:
        try:
            fetch_run = run_html_index_probe_for_source(db, source, timeout_seconds=timeout_seconds)

            if fetch_run.status == "success":
                success_count += 1
            else:
                failed_count += 1

            items_found_total += fetch_run.items_found
            items_new_total += fetch_run.items_new
            items_updated_total += fetch_run.items_updated
            items_failed_total += fetch_run.items_failed

        except Exception:
            failed_count += 1

    return {
        "sources_total": total,
        "sources_success": success_count,
        "sources_failed": failed_count,
        "items_found": items_found_total,
        "items_new": items_new_total,
        "items_updated": items_updated_total,
        "items_failed": items_failed_total,
    }
