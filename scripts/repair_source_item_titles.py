#!/usr/bin/env python3
"""
repair_source_item_titles.py — Repair weak/bad titles in existing SourceItems.

Scans SourceItems with titles like "FEATURED", "Learn More", "Read More", etc.,
fetches the article detail page to get the real title, and updates the record.

Usage:
    python scripts/repair_source_item_titles.py                       # dry-run (default)
    python scripts/repair_source_item_titles.py --apply             # actually write to DB
    python scripts/repair_source_item_titles.py --source-key meta_ai_blog
    python scripts/repair_source_item_titles.py --source-key meta_ai_blog --apply

Exit codes:
    0 = success (dry-run shows no changes needed, or apply completed)
    1 = error
"""
from __future__ import annotations

import argparse
import json
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import SourceItem
from app.sources.html_index_probe import (
    fetch_article_metadata,
    choose_candidate_title,
    _is_weak_title,
)

# Allow override via environment for testing
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./data/ai_frontier_radar.db",
)


def build_session():
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    Session = sessionmaker(bind=engine)
    return Session()


def repair_titles(apply: bool = False, source_key: str | None = None) -> dict:
    """Scan and optionally repair SourceItems with weak titles.

    Args:
        apply: If True, write changes to the database. If False, only report.
        source_key: If set, only process SourceItems from this source.

    Returns:
        dict with stats: total_scanned, weak_found, would_fix (or fixed if apply=True)
    """
    session = build_session()

    # Build query: only SourceItems with weak titles
    query = session.query(SourceItem)
    if source_key:
        query = query.filter(SourceItem.source_key == source_key)

    all_items = query.all()
    stats = {"total_scanned": 0, "weak_found": 0, "would_fix": 0, "fixed": 0, "errors": 0}

    for item in all_items:
        stats["total_scanned"] += 1

        if not _is_weak_title(item.title or ""):
            continue

        stats["weak_found"] += 1
        old_title = item.title or "(empty)"

        # Fetch article detail page metadata
        detail = fetch_article_metadata(item.url, timeout_seconds=5.0)

        # Choose best title
        new_title, title_source = choose_candidate_title(
            item.title or "", item.url, detail
        )

        if apply:
            try:
                item.title = new_title
                raw_meta = json.loads(item.raw_metadata_json or "{}")
                raw_meta["title_source"] = title_source
                raw_meta["detail_title"] = detail.get("title")
                raw_meta["detail_description"] = detail.get("description")
                raw_meta["detail_fetch_error"] = detail.get("fetch_error")
                raw_meta["repaired_at"] = datetime.utcnow().isoformat()
                item.raw_metadata_json = json.dumps(raw_meta, ensure_ascii=False)
                session.commit()
                stats["fixed"] += 1
                print(f"  [FIXED] #{item.id} | {old_title!r:30s} → {new_title!r} (source={title_source})")
            except Exception as exc:
                session.rollback()
                stats["errors"] += 1
                print(f"  [ERROR] #{item.id} {item.url} — {exc}")
        else:
            stats["would_fix"] += 1
            new_title_preview = f"{new_title[:60]}{'...' if len(new_title) > 60 else ''}"
            print(f"  [WOULD FIX] #{item.id} | {old_title!r:30s} → {new_title_preview!r} "
                  f"(source={title_source}, detail_title={detail.get('title', 'N/A')!r})")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Repair weak titles (FEATURED / Learn More / etc.) in SourceItems. "
                    "Run without --apply for dry-run."
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Actually write changes to the database (default: dry-run)"
    )
    parser.add_argument(
        "--source-key",
        help="Only process SourceItems from this source_key (e.g. meta_ai_blog)"
    )
    args = parser.parse_args()

    mode = "DRY-RUN" if not args.apply else "APPLY"
    print(f"\n=== repair_source_item_titles.py [{mode}] ===")
    if args.source_key:
        print(f"  source_key filter: {args.source_key}")
    print()

    try:
        stats = repair_titles(apply=args.apply, source_key=args.source_key)
    except Exception as exc:
        print(f"[FATAL] {exc}")
        sys.exit(1)

    print()
    print(f"Scanned:   {stats['total_scanned']}")
    print(f"Weak:      {stats['weak_found']}")
    if args.apply:
        print(f"Fixed:     {stats['fixed']}")
        print(f"Errors:    {stats['errors']}")
    else:
        print(f"Would fix: {stats['would_fix']}")

    if not args.apply:
        print()
        print("No changes written. Run with --apply to apply fixes.")

    sys.exit(0)


if __name__ == "__main__":
    main()
