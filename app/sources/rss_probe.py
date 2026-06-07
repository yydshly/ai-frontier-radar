"""RSS Source probing — discovers items from RSS/Atom feeds.

Does NOT fetch article body, does NOT call LLM.
"""
import json
from datetime import datetime

import feedparser
import httpx
from sqlalchemy.orm import Session

from app.models import Source, SourceItem, FetchRun


def probe_rss_source(db: Session, source: Source, timeout_seconds: int = 20) -> dict:
    """Probe a single RSS source and discover items.

    Args:
        db: SQLAlchemy session.
        source: Source ORM object with feed_url set.
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
    }

    # Validate feed_url
    if not source.feed_url:
        result["error_message"] = "feed_url is not set"
        return result

    # Fetch feed
    try:
        response = httpx.get(source.feed_url, timeout=timeout_seconds, follow_redirects=True)
        response.raise_for_status()
    except httpx.TimeoutException:
        result["error_message"] = f"Timeout fetching feed after {timeout_seconds}s"
        return result
    except httpx.HTTPStatusError as e:
        result["error_message"] = f"HTTP {e.response.status_code}: {e.response.reason_phrase}"
        return result
    except Exception as e:
        result["error_message"] = f"Request failed: {e}"
        return result

    # Parse feed
    try:
        feed = feedparser.parse(response.text)
    except Exception as e:
        result["error_message"] = f"Failed to parse feed: {e}"
        return result

    if feed.bozo and not feed.entries:
        result["error_message"] = "Feed is malformed or empty"
        return result

    # Process entries
    for entry in feed.entries:
        result["items_found"] += 1

        # Get URL — required
        url = getattr(entry, "link", None)
        if not url:
            result["items_failed"] += 1
            continue

        # Canonical URL equals URL for RSS items
        canonical_url = url

        # Extract metadata
        title = getattr(entry, "title", None) or None
        author = getattr(entry, "author", None) or None

        # published or updated
        published_at = None
        if hasattr(entry, "published") and entry.published:
            published_at = entry.published
        elif hasattr(entry, "updated") and entry.updated:
            published_at = entry.updated

        # Raw metadata as JSON
        raw_metadata = {
            "title": title,
            "author": author,
            "published": published_at,
            "link": url,
            "summary": getattr(entry, "summary", None),
        }

        # Check if item already exists
        existing = (
            db.query(SourceItem)
            .filter(SourceItem.source_id == source.id, SourceItem.url == url)
            .first()
        )

        if existing is None:
            # Create new SourceItem
            item = SourceItem(
                source_id=source.id,
                source_key=source.source_key,
                url=url,
                canonical_url=canonical_url,
                title=title,
                author=author,
                published_at=published_at,
                raw_metadata_json=json.dumps(raw_metadata, ensure_ascii=False),
                status="discovered",
                last_seen_at=datetime.utcnow(),
            )
            db.add(item)
            result["items_new"] += 1
        else:
            # Update existing item's metadata and last_seen_at
            existing.title = title
            existing.author = author
            existing.published_at = published_at
            existing.raw_metadata_json = json.dumps(raw_metadata, ensure_ascii=False)
            existing.last_seen_at = datetime.utcnow()
            result["items_updated"] += 1

    db.commit()
    return result


def run_rss_probe_for_source(db: Session, source: Source, timeout_seconds: int = 20) -> FetchRun:
    """Run RSS probe for a single source and record a FetchRun.

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
        # Probe the source
        probe_result = probe_rss_source(db, source, timeout_seconds=timeout_seconds)

        # Update fetch run
        fetch_run.items_found = probe_result["items_found"]
        fetch_run.items_new = probe_result["items_new"]
        fetch_run.items_updated = probe_result["items_updated"]
        fetch_run.items_failed = probe_result["items_failed"]
        fetch_run.finished_at = datetime.utcnow()

        items_found = probe_result["items_found"]
        items_failed = probe_result["items_failed"]
        error_message = probe_result["error_message"]

        if error_message:
            # Feed fetch/parse failure — always "failed"
            fetch_run.status = "failed"
            fetch_run.error_message = error_message

            # Update source with error state
            source.last_checked_at = datetime.utcnow()
            source.last_error_message = error_message
            # Do NOT update last_success_at
        elif items_failed > 0 and items_found > items_failed:
            # Some items failed during parsing — partial success
            fetch_run.status = "partial_failed"
            fetch_run.error_message = f"{items_failed} item(s) failed during RSS entry parsing"

            # Update source — partial success still updates last_success_at
            source.last_checked_at = datetime.utcnow()
            source.last_success_at = datetime.utcnow()
            source.last_error_message = fetch_run.error_message
        elif items_failed > 0 and items_found == items_failed:
            # All entries failed during parsing — complete failure
            fetch_run.status = "failed"
            fetch_run.error_message = "All RSS entries failed during parsing"

            source.last_checked_at = datetime.utcnow()
            source.last_error_message = fetch_run.error_message
        else:
            # All entries succeeded
            fetch_run.status = "success"
            fetch_run.error_message = None

            source.last_checked_at = datetime.utcnow()
            source.last_success_at = datetime.utcnow()
            source.last_error_message = None

        db.commit()
        db.refresh(fetch_run)
        return fetch_run

    except Exception as e:
        # Rollback any uncommitted changes from the probe
        db.rollback()

        # Record failure in fetch run
        fetch_run.status = "failed"
        fetch_run.error_message = str(e)
        fetch_run.finished_at = datetime.utcnow()

        # Update source with error state
        source.last_checked_at = datetime.utcnow()
        source.last_error_message = str(e)

        db.commit()
        db.refresh(fetch_run)
        return fetch_run


def run_rss_probe_for_enabled_sources(
    db: Session,
    source_key: str | None = None,
    limit_sources: int | None = None,
    timeout_seconds: int = 20,
) -> dict:
    """Run RSS probe for enabled RSS sources.

    Args:
        db: SQLAlchemy session.
        source_key: If set, only probe this specific source_key.
        limit_sources: If set, probe at most this many sources.
        timeout_seconds: HTTP request timeout.

    Returns:
        dict with aggregate statistics across all RSS sources.
    """
    # Find enabled RSS sources
    query = db.query(Source).filter(
        Source.enabled == True, Source.fetch_strategy == "rss"
    )

    if source_key is not None:
        query = query.filter(Source.source_key == source_key)

    enabled_rss_sources = query.all()

    if limit_sources is not None:
        enabled_rss_sources = enabled_rss_sources[:limit_sources]

    total = len(enabled_rss_sources)
    success_count = 0
    failed_count = 0

    items_found_total = 0
    items_new_total = 0
    items_updated_total = 0
    items_failed_total = 0

    for source in enabled_rss_sources:
        try:
            fetch_run = run_rss_probe_for_source(db, source, timeout_seconds=timeout_seconds)

            if fetch_run.status == "success":
                success_count += 1
            else:
                failed_count += 1

            items_found_total += fetch_run.items_found
            items_new_total += fetch_run.items_new
            items_updated_total += fetch_run.items_updated
            items_failed_total += fetch_run.items_failed

        except Exception as e:
            # Source-level failure — still count as failed
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
