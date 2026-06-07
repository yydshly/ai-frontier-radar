#!/usr/bin/env python3
"""
Check for historical SourceItems that look like listing/pagination pages.

This script is READ-ONLY: it scans the current database for SourceItems whose
URLs match patterns that V0.3.3 onwards block (e.g., /blog?p=2, /news?page=2).

It does NOT delete or modify any data. Use the output to decide whether to
clean up old data manually or rebuild the local database.

Usage:
    python scripts/check_listing_source_items.py
    python scripts/check_listing_source_items.py --source-key huggingface_blog
    python scripts/check_listing_source_items.py --limit 100
"""
import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Check for historical SourceItems that look like listing/pagination pages. Read-only."
    )
    parser.add_argument(
        "--source-key",
        type=str,
        default=None,
        help="Only check SourceItems for the given source_key.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=200,
        help="Maximum number of suspected items to print (default: 200).",
    )
    return parser


def _check_listing_source_items(source_key=None, limit=200):
    """Scan the database for SourceItems that look like listing/pagination pages.

    Args:
        source_key: If set, only check this source_key.
        limit: Maximum number of results to print.

    Returns:
        Number of suspected listing items found.
    """
    # Imports inside function so env / DB is loaded by caller context
    from app.db import SessionLocal
    from app.models import Source, SourceItem
    from app.sources.html_index_probe import _is_index_or_listing_url

    db = SessionLocal()
    try:
        # Build base query
        query = db.query(SourceItem, Source).outerjoin(
            Source, SourceItem.source_id == Source.id
        )
        if source_key:
            query = query.filter(SourceItem.source_key == source_key)

        # Order by id desc so newest are first
        query = query.order_by(SourceItem.id.desc())

        rows = query.all()

        if not rows:
            print("No SourceItems found in database.")
            return 0

        suspected = []
        for item, source in rows:
            url = item.url or ""
            if not url:
                continue

            homepage = source.homepage_url if source else ""
            if not homepage:
                # No homepage means we can't apply the same-domain rule
                # Use a permissive check: just look at path/query
                if _looks_like_listing_url_no_homepage(url):
                    suspected.append({
                        "id": item.id,
                        "source_key": item.source_key,
                        "status": item.status,
                        "url": url,
                        "title": item.title,
                        "reason": "source_missing_homepage_url",
                    })
                continue

            if _is_index_or_listing_url(url, homepage):
                suspected.append({
                    "id": item.id,
                    "source_key": item.source_key,
                    "status": item.status,
                    "url": url,
                    "title": item.title,
                    "reason": "matched_listing_rule",
                })

        # Print results
        if not suspected:
            print("No suspected listing SourceItems found.")
            return 0

        print(f"Potential listing SourceItems:")
        shown = suspected[:limit]
        for s in shown:
            title = s["title"] or "(no title)"
            print(
                f"  #{s['id']:<5} {s['source_key']:<22} {s['status']:<10} {s['url'][:80]}"
            )
        if len(suspected) > limit:
            print(f"  ... and {len(suspected) - limit} more (use --limit to show more)")

        print(f"\nTotal suspected listing items: {len(suspected)}")
        return len(suspected)
    finally:
        db.close()


def _looks_like_listing_url_no_homepage(url: str) -> bool:
    """Conservative listing check for items where we don't have a homepage URL.

    Only matches obvious listing patterns to avoid false positives.
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    path = parsed.path.lower().rstrip("/")
    path_segments = [seg for seg in path.split("/") if seg]

    listing_paths = {"blog", "news", "research", "articles", "posts",
                     "announcements", "updates", "reports"}

    if len(path_segments) == 1 and path_segments[0] in listing_paths:
        return True

    # Check for pagination/listing query params
    from urllib.parse import parse_qs
    qs = parse_qs(parsed.query, keep_blank_values=True)
    listing_params = {"p", "page", "paged", "offset", "start",
                      "sort", "filter", "tag", "tags", "category",
                      "search", "q", "author", "topic"}
    for param in qs:
        if param.lower() in listing_params:
            return True

    return False


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()
    count = _check_listing_source_items(
        source_key=args.source_key,
        limit=args.limit,
    )
    return 0 if count >= 0 else 1


if __name__ == "__main__":
    sys.exit(main())
