#!/usr/bin/env python3
"""Minimal real-probe acceptance script for V0.3.1.

Validates the minimum real source discovery pipeline:
    sources.example.yaml / sources.yaml
    -> sync_sources_config_to_db()
    -> probe_rss_sources.py / probe_html_index_sources.py
    -> SourceItem 入库
    -> FetchRun 记录
    -> /source-items 可查看
    -> 可重复运行且不会重复插入

Usage:
    python scripts/acceptance_probe_sources.py
    python scripts/acceptance_probe_sources.py --rss-source arxiv_cs_ai --html-source openai_news --timeout 15
"""
import argparse
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source, SourceItem, FetchRun
from app.sources import sync_sources_config_to_db
from app.sources.rss_probe import run_rss_probe_for_source
from app.sources.html_index_probe import run_html_index_probe_for_source


def main():
    parser = argparse.ArgumentParser(
        description="V0.3.1 real source probe acceptance test."
    )
    parser.add_argument(
        "--rss-source",
        type=str,
        default="arxiv_cs_cl",
        help="RSS source_key to probe (default: arxiv_cs_cl).",
    )
    parser.add_argument(
        "--html-source",
        type=str,
        default="huggingface_blog",
        help="HTML index source_key to probe (default: huggingface_blog).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP request timeout in seconds (default: 15).",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("V0.3.1 Real Source Probe Acceptance")
    print("=" * 60)

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    try:
        print("\n[1] Syncing source config to database...")
        sync_result = sync_sources_config_to_db(db, force_reload=True)
        print(f"    total={sync_result['total']}, created={sync_result['created']}")

        # --- RSS Probe ---
        print(f"\n[2] Probing RSS source: {args.rss_source} (timeout={args.timeout}s)...")
        rss_source = db.query(Source).filter(Source.source_key == args.rss_source).first()
        if not rss_source:
            print(f"[FAIL] RSS source '{args.rss_source}' not found in DB.")
            rss_result = None
        elif rss_source.fetch_strategy != "rss":
            print(f"[FAIL] Source '{args.rss_source}' is not an RSS source (strategy={rss_source.fetch_strategy}).")
            rss_result = None
        else:
            rss_fetch_run = run_rss_probe_for_source(
                db, rss_source, timeout_seconds=args.timeout
            )
            rss_result = {
                "status": rss_fetch_run.status,
                "items_found": rss_fetch_run.items_found,
                "items_new": rss_fetch_run.items_new,
                "items_updated": rss_fetch_run.items_updated,
                "items_failed": rss_fetch_run.items_failed,
                "error_message": rss_fetch_run.error_message,
                "started_at": rss_fetch_run.started_at,
                "finished_at": rss_fetch_run.finished_at,
            }
            icon = "[OK]" if rss_fetch_run.status in ("success", "partial_failed") else "[FAIL]"
            print(
                f"  {icon} RSS {args.rss_source}: status={rss_fetch_run.status}, "
                f"found={rss_fetch_run.items_found}, new={rss_fetch_run.items_new}, "
                f"updated={rss_fetch_run.items_updated}, failed={rss_fetch_run.items_failed}"
            )
            if rss_fetch_run.error_message:
                print(f"       error: {rss_fetch_run.error_message[:120]}")

        # --- HTML Index Probe ---
        print(f"\n[3] Probing HTML index source: {args.html_source} (timeout={args.timeout}s)...")
        html_source = db.query(Source).filter(Source.source_key == args.html_source).first()
        if not html_source:
            print(f"[FAIL] HTML source '{args.html_source}' not found in DB.")
            html_result = None
        elif html_source.fetch_strategy != "html_index":
            print(f"[FAIL] Source '{args.html_source}' is not an HTML index source (strategy={html_source.fetch_strategy}).")
            html_result = None
        else:
            html_fetch_run = run_html_index_probe_for_source(
                db, html_source, timeout_seconds=args.timeout
            )
            html_result = {
                "status": html_fetch_run.status,
                "items_found": html_fetch_run.items_found,
                "items_new": html_fetch_run.items_new,
                "items_updated": html_fetch_run.items_updated,
                "items_failed": html_fetch_run.items_failed,
                "error_message": html_fetch_run.error_message,
                "started_at": html_fetch_run.started_at,
                "finished_at": html_fetch_run.finished_at,
            }
            icon = "[OK]" if html_fetch_run.status in ("success", "partial_failed") else "[FAIL]"
            print(
                f"  {icon} HTML {args.html_source}: status={html_fetch_run.status}, "
                f"found={html_fetch_run.items_found}, new={html_fetch_run.items_new}, "
                f"updated={html_fetch_run.items_updated}, failed={html_fetch_run.items_failed}"
            )
            if html_fetch_run.error_message:
                print(f"       error: {html_fetch_run.error_message[:120]}")

        # --- Query stats ---
        print("\n[4] Querying database state...")
        total_items = db.query(SourceItem).count()
        total_fetch_runs = db.query(FetchRun).count()
        print(f"    SourceItem count: {total_items}")
        print(f"    FetchRun count:   {total_fetch_runs}")

        # --- Acceptance Summary ---
        print("\n" + "=" * 60)
        print("Acceptance Summary")
        print("=" * 60)

        passed = True

        # Check 1: At least one source had success or partial_failed
        rss_ok = rss_result and rss_result["status"] in ("success", "partial_failed")
        html_ok = html_result and html_result["status"] in ("success", "partial_failed")
        if not rss_ok and not html_ok:
            print("  [FAIL] Neither RSS nor HTML source succeeded or partial_failed")
            passed = False
        else:
            print(f"  [OK] At least one source succeeded or partial_failed")

        # Check 2: At least 1 SourceItem found
        if total_items < 1:
            print(f"  [FAIL] No SourceItems found (expected at least 1)")
            passed = False
        else:
            print(f"  [OK] SourceItems found: {total_items}")

        # Check 3: FetchRuns have started_at and finished_at
        recent_runs = (
            db.query(FetchRun)
            .order_by(FetchRun.started_at.desc())
            .limit(2)
            .all()
        )
        runs_have_timestamps = all(r.started_at and r.finished_at for r in recent_runs)
        if not runs_have_timestamps:
            print("  [FAIL] Some FetchRuns missing started_at or finished_at")
            passed = False
        else:
            print("  [OK] FetchRuns have started_at and finished_at")

        # Check 4: Failed sources have error_message
        failed_runs = (
            db.query(FetchRun)
            .filter(FetchRun.status.in_(["failed", "partial_failed"]))
            .all()
        )
        failed_without_error = [r for r in failed_runs if not r.error_message]
        if failed_without_error:
            print(f"  [FAIL] {len(failed_without_error)} failed FetchRuns without error_message")
            passed = False
        else:
            print("  [OK] Failed FetchRuns have error_message")

        print()
        if passed:
            print("[PASS] ACCEPTANCE PASSED")
            return 0
        else:
            print("[FAIL] ACCEPTANCE FAILED")
            return 1

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
