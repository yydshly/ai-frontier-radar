#!/usr/bin/env python3
"""Probe all enabled RSS sources and save discovered items to the database.

Usage:
    python scripts/probe_rss_sources.py
"""
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source
from app.sources import sync_sources_config_to_db
from app.sources.rss_probe import run_rss_probe_for_enabled_sources


def main():
    print("=" * 60)
    print("RSS Source Probe")
    print("=" * 60)

    # Initialize database
    init_db()
    print("[OK] Database initialized")

    # Sync sources config to DB
    db = SessionLocal()
    try:
        print("\n[1] Syncing source config to database...")
        sync_result = sync_sources_config_to_db(db, force_reload=True)
        print(f"    total={sync_result['total']}, "
              f"created={sync_result['created']}, "
              f"updated={sync_result['updated']}")

        # Find enabled RSS sources
        rss_sources = (
            db.query(Source)
            .filter(Source.enabled == True, Source.fetch_strategy == "rss")
            .all()
        )
        print(f"\n[2] Found {len(rss_sources)} enabled RSS sources:")
        for s in rss_sources:
            print(f"    - {s.source_key}: {s.feed_url}")

        if not rss_sources:
            print("[WARN] No enabled RSS sources found in database")
            return 0

        # Run probe for all enabled RSS sources
        print(f"\n[3] Probing RSS sources...")
        result = run_rss_probe_for_enabled_sources(db)

        print(f"\n--- Aggregate Results ---")
        print(f"  Sources total:    {result['sources_total']}")
        print(f"  Sources success:  {result['sources_success']}")
        print(f"  Sources failed:   {result['sources_failed']}")
        print(f"  Items found:      {result['items_found']}")
        print(f"  Items new:        {result['items_new']}")
        print(f"  Items updated:    {result['items_updated']}")
        print(f"  Items failed:     {result['items_failed']}")

        # Detailed per-source results
        print(f"\n--- Per-Source Results ---")
        for source in rss_sources:
            # Get latest fetch run for this source
            from app.models import FetchRun
            latest_run = (
                db.query(FetchRun)
                .filter(FetchRun.source_id == source.id)
                .order_by(FetchRun.started_at.desc())
                .first()
            )
            if latest_run:
                status_icon = "✅" if latest_run.status == "success" else "❌"
                print(f"  {status_icon} {source.source_key}: "
                      f"found={latest_run.items_found}, "
                      f"new={latest_run.items_new}, "
                      f"updated={latest_run.items_updated}, "
                      f"failed={latest_run.items_failed}, "
                      f"status={latest_run.status}")
                if latest_run.error_message:
                    print(f"       error: {latest_run.error_message[:80]}")

        # Determine exit code
        if result["sources_failed"] == 0:
            print("\n[OK] All RSS sources probed successfully")
            return 0
        elif result["sources_success"] > 0:
            print(f"\n[WARN] {result['sources_failed']} source(s) failed")
            return 0  # Partial success is not an error for this script
        else:
            print("\n[FAIL] All RSS sources failed")
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
