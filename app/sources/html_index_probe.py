"""HTML Index Source probing — discovers article links from index pages.

Does NOT fetch article body, does NOT call LLM.
"""
import json
import re
from datetime import datetime
from urllib.parse import urljoin, urlparse, urldefrag

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.models import Source, SourceItem, FetchRun

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

# Regex for 4-digit year in path
YEAR_PATTERN = re.compile(r"/\d{4}/|" r"-\d{4}/|" r"/\d{4}$")


def _is_probable_article_url(url: str, source_homepage_url: str) -> bool:
    """Filter URL to decide if it looks like a probable article/research page.

    Args:
        url: Absolute URL to evaluate.
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
        "User-Agent": "AI-Frontier-Radar/0.2 (+https://github.com/yydshly/ai-frontier-radar)"
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

        # Join with homepage to get absolute URL
        absolute_url, _ = urldefrag(urljoin(source.homepage_url, href))
        if not absolute_url:
            continue

        # Filter using heuristic
        if not _is_probable_article_url(absolute_url, source.homepage_url):
            continue

        # Get link text
        link_text = a_tag.get_text(strip=True)

        # Use URL path as fallback for title
        parsed_url = urlparse(absolute_url)
        path_segments = [s for s in parsed_url.path.split("/") if s]
        if link_text:
            title = link_text
        elif path_segments:
            title = path_segments[-1].replace("-", " ").replace("_", " ").strip()
        else:
            title = absolute_url

        candidates.append({
            "url": absolute_url,
            "title": title,
            "link_text": link_text,
        })

        # Cap at 50 candidates to avoid noise
        if len(candidates) >= 50:
            break

    # If no candidates found, return partial failure
    if not candidates:
        result["error_message"] = "No candidate article links found"
        result["error_kind"] = "no_candidates"
        return result

    # Process each candidate
    for candidate in candidates:
        result["items_found"] += 1

        # Check if item already exists
        existing = (
            db.query(SourceItem)
            .filter(SourceItem.source_id == source.id, SourceItem.url == candidate["url"])
            .first()
        )

        raw_metadata = {
            "link_text": candidate["link_text"],
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
            # Update existing item
            existing.title = candidate["title"]
            existing.raw_metadata_json = json.dumps(raw_metadata, ensure_ascii=False)
            existing.last_seen_at = datetime.utcnow()
            result["items_updated"] += 1

    db.commit()
    return result


def run_html_index_probe_for_source(db: Session, source: Source) -> FetchRun:
    """Run HTML index probe for a single source and record a FetchRun.

    Args:
        db: SQLAlchemy session.
        source: Source ORM object.

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
        probe_result = probe_html_index_source(db, source)

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


def run_html_index_probe_for_enabled_sources(db: Session) -> dict:
    """Run HTML index probe for all enabled HTML index sources.

    Args:
        db: SQLAlchemy session.

    Returns:
        dict with aggregate statistics across all HTML index sources.
    """
    enabled_html_sources = (
        db.query(Source)
        .filter(Source.enabled == True, Source.fetch_strategy == "html_index")
        .all()
    )

    total = len(enabled_html_sources)
    success_count = 0
    failed_count = 0

    items_found_total = 0
    items_new_total = 0
    items_updated_total = 0
    items_failed_total = 0

    for source in enabled_html_sources:
        try:
            fetch_run = run_html_index_probe_for_source(db, source)

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
