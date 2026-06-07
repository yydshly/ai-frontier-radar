#!/usr/bin/env python3
"""V0.7 quality check script for SourceItems.

Scans existing SourceItems and reports quality issues:
- suspected listing/pagination URLs
- empty titles
- duplicate URLs
- items from specific source_key

This script is read-only (no DB writes).

Usage:
    python scripts/check_source_item_quality.py
    python scripts/check_source_item_quality.py --source-key anthropic_news
    python scripts/check_source_item_quality.py --source-key deepmind_blog
    python scripts/check_source_item_quality.py --limit 100
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source, SourceItem
from app.sources.html_index_probe import _is_index_or_listing_url


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="Check SourceItem quality — read-only, no DB writes."
    )
    parser.add_argument(
        "--source-key",
        type=str,
        default=None,
        help="Filter to a specific source_key.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of items scanned per source (for performance).",
    )
    return parser


def _run_quality_check(args):
    print("=" * 60)
    print("SourceItem Quality Report")
    print("=" * 60)

    init_db()
    db = SessionLocal()
    try:
        # Build query
        query = db.query(SourceItem)
        if args.source_key:
            query = query.filter(SourceItem.source_key == args.source_key)

        if args.limit:
            items = query.limit(args.limit).all()
        else:
            items = query.all()

        if not items:
            print("\n[INFO] No SourceItems found in database.")
            if args.source_key:
                print(f"[INFO] No items for source_key='{args.source_key}'.")
                # Check if source exists
                src = db.query(Source).filter(Source.source_key == args.source_key).first()
                if not src:
                    print(f"[FAIL] Source '{args.source_key}' does not exist in registry.")
                    return 1
                else:
                    print(f"[INFO] Source '{args.source_key}' exists but has no SourceItems yet.")
                    print(f"[INFO] Try running acceptance_real_source_coverage.py first.")
                    return 0
            return 0

        # Group by source_key
        by_source: dict[str, list[SourceItem]] = defaultdict(list)
        for item in items:
            by_source[item.source_key].append(item)

        total_empty_title = 0
        total_suspected_listing = 0
        total_duplicate = 0

        for source_key, source_items in sorted(by_source.items()):
            src = db.query(Source).filter(Source.source_key == source_key).first()
            homepage_url = src.homepage_url if src else ""

            # Quality metrics
            empty_title = [i for i in source_items if not i.title or not i.title.strip()]
            suspected_listing = [
                i for i in source_items
                if _is_index_or_listing_url(i.url, homepage_url or "")
            ]

            # Duplicate URLs
            url_counts: dict[str, list[int]] = defaultdict(list)
            for i in source_items:
                url_counts[i.url].append(i.id)
            duplicates = {url: ids for url, ids in url_counts.items() if len(ids) > 1}
            dup_count = sum(len(ids) - 1 for ids in duplicates.values())

            total_empty_title += len(empty_title)
            total_suspected_listing += len(suspected_listing)
            total_duplicate += dup_count

            print(f"\n{'─' * 50}")
            print(f"  {source_key}  (total={len(source_items)})")
            print(f"  empty_title_count: {len(empty_title)}")
            print(f"  suspected_listing_count: {len(suspected_listing)}")
            print(f"  duplicate_url_count: {dup_count}")

            if suspected_listing:
                print(f"  ⚠ WARNING: suspected listing/pagination URLs found:")
                for it in suspected_listing[:5]:
                    print(f"    - {it.url[:80]}")
                if len(suspected_listing) > 5:
                    print(f"    ... and {len(suspected_listing) - 5} more")

            if empty_title:
                print(f"  sample empty-title items:")
                for it in empty_title[:3]:
                    print(f"    - id={it.id}: {it.url[:80]}")

            if duplicates:
                print(f"  sample duplicate URLs:")
                for url, ids in list(duplicates.items())[:3]:
                    print(f"    - {url[:80]} (ids: {ids})")

        print(f"\n{'═' * 50}")
        print(f"  Grand Total")
        print(f"  total items scanned: {len(items)}")
        print(f"  total empty_title: {total_empty_title}")
        print(f"  total suspected_listing: {total_suspected_listing}")
        print(f"  total duplicate_url: {total_duplicate}")
        print(f"{'═' * 50}")

        if total_suspected_listing > 0:
            print(f"\n⚠ WARNING: {total_suspected_listing} suspected listing/pagination URL(s) found.")
            print("  These may need filtering rules to be updated in html_index_probe.py.")

        if total_empty_title > 0:
            print(f"\n⚠ WARNING: {total_empty_title} item(s) have empty titles.")

        if total_duplicate > 0:
            print(f"\n⚠ WARNING: {total_duplicate} duplicate URL(s) found.")

        if total_suspected_listing == 0 and total_empty_title == 0 and total_duplicate == 0:
            print("\n✅ All scanned SourceItems look clean!")

        return 0

    finally:
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()
    return _run_quality_check(args)


if __name__ == "__main__":
    sys.exit(main())
