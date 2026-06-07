#!/usr/bin/env python3
"""Probe HTML index sources and save discovered article links to the database.

Usage:
    python scripts/probe_html_index_sources.py
    python scripts/probe_html_index_sources.py --source-key openai_news
    python scripts/probe_html_index_sources.py --limit-sources 2
    python scripts/probe_html_index_sources.py --timeout 15
"""
import argparse
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source, FetchRun
from app.sources import sync_sources_config_to_db
from app.sources.html_index_probe import run_html_index_probe_for_enabled_sources


def main():
    parser = argparse.ArgumentParser(
        description="Probe HTML index sources and save discovered article links."
    )
    parser.add_argument(
        "--source-key",
        type=str,
        default=None,
        help="Only probe this specific source_key.",
    )
    parser.add_argument(
        "--limit-sources",
        type=int,
        default=None,
        help="Probe at most N sources (applies when no --source-key specified).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP request timeout in seconds (default: 20).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("HTML Index Source Probe")
    print("=" * 60)

    # Initialize database
    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    try:
        # Sync sources config to DB
        print("\n[1] Syncing source config to database...")
        sync_result = sync_sources_config_to_db(db, force_reload=True)
        print(f"    total={sync_result['total']}, "
              f"created={sync_result['created']}, "
              f"updated={sync_result['updated']}")

        # Find HTML index sources to probe
        query = db.query(Source).filter(
            Source.enabled == True, Source.fetch_strategy == "html_index"
        )
        if args.source_key:
            query = query.filter(Source.source_key == args.source_key)

        html_sources = query.all()
        if args.limit_sources is not None and args.source_key is None:
            html_sources = html_sources[:args.limit_sources]

        print(f"\n[2] Targeting {len(html_sources)} enabled HTML index source(s):")
        for s in html_sources:
            print(f"    - {s.source_key}: {s.homepage_url}")

        if args.source_key and not html_sources:
            # Check if the key exists but is not html_index
            existing = db.query(Source).filter(Source.source_key == args.source_key).first()
            if existing:
                print(
                    f"[FAIL] Source '{args.source_key}' exists but has fetch_strategy='{existing.fetch_strategy}', "
                    f"not 'html_index'."
                )
            else:
                print(f"[FAIL] Source '{args.source_key}' not found in registry.")
            return 1

        if not html_sources:
            print("[WARN] No enabled HTML index sources found in database")
            return 0

        # Run probe
        print(f"\n[3] Probing HTML index sources (timeout={args.timeout}s)...")
        result = run_html_index_probe_for_enabled_sources(
            db,
            source_key=args.source_key,
            limit_sources=args.limit_sources,
            timeout_seconds=args.timeout,
        )

        print(f"\n--- Aggregate Results ---")
        print(f"  Sources total:    {result['sources_total']}")
        print(f"  Sources success:  {result['sources_success']}")
        print(f"  Sources failed:   {result['sources_failed']}")
        print(f"  Items found:     {result['items_found']}")
        print(f"  Items new:       {result['items_new']}")
        print(f"  Items updated:   {result['items_updated']}")
        print(f"  Items failed:    {result['items_failed']}")

        # Detailed per-source results
        print(f"\n--- Per-Source Results ---")
        for source in html_sources:
            latest_run = (
                db.query(FetchRun)
                .filter(FetchRun.source_id == source.id)
                .order_by(FetchRun.started_at.desc())
                .first()
            )
            if latest_run:
                status_icon = "[OK]" if latest_run.status == "success" else "[FAIL]"
                print(f"  {status_icon} {source.source_key}: "
                      f"found={latest_run.items_found}, "
                      f"new={latest_run.items_new}, "
                      f"updated={latest_run.items_updated}, "
                      f"failed={latest_run.items_failed}, "
                      f"status={latest_run.status}")
                if latest_run.error_message:
                    print(f"       error: {latest_run.error_message[:120]}")

        # Determine exit code
        if result["sources_failed"] == 0:
            print("\n[OK] All HTML index sources probed successfully")
            return 0
        elif result["sources_success"] > 0:
            print(f"\n[WARN] {result['sources_failed']} source(s) failed")
            return 0  # Partial success is not an error for this script
        else:
            print("\n[FAIL] All HTML index sources failed")
            return 1

    except Exception as e:
        print(f"\n[FAIL] Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
