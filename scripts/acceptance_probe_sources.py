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
    python scripts/acceptance_probe_sources.py --isolated-db --repeat 2 --timeout 15
    python scripts/acceptance_probe_sources.py --rss-source arxiv_cs_cl --html-source deepmind_blog
"""
import argparse
import os
import sys
import time
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _build_arg_parser():
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
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB (data/acceptance_probe.db) instead of the default DB.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after acceptance (default: delete it after).",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of times to repeat the probe run for idempotency check (default: 1).",
    )
    return parser


def _run_acceptance(args):
    """Run one acceptance iteration. Returns (rss_result, html_result, before/after stats)."""
    # Imports are done here so --isolated-db can set env before they load
    from app.db import SessionLocal, init_db
    from app.models import Source, SourceItem, FetchRun
    from app.sources import sync_sources_config_to_db
    from app.sources.rss_probe import run_rss_probe_for_source
    from app.sources.html_index_probe import run_html_index_probe_for_source

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

        # Before stats per source
        rss_before = db.query(SourceItem).filter(SourceItem.source_key == args.rss_source).count()
        html_before = db.query(SourceItem).filter(SourceItem.source_key == args.html_source).count()

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
            }
            icon = "[OK]" if html_fetch_run.status in ("success", "partial_failed") else "[FAIL]"
            print(
                f"  {icon} HTML {args.html_source}: status={html_fetch_run.status}, "
                f"found={html_fetch_run.items_found}, new={html_fetch_run.items_new}, "
                f"updated={html_fetch_run.items_updated}, failed={html_fetch_run.items_failed}"
            )
            if html_fetch_run.error_message:
                print(f"       error: {html_fetch_run.error_message[:120]}")

        # After stats per source
        rss_after = db.query(SourceItem).filter(SourceItem.source_key == args.rss_source).count()
        html_after = db.query(SourceItem).filter(SourceItem.source_key == args.html_source).count()

        print(f"\n[4] SourceItem before/after by source:")
        print(f"    {args.rss_source}: before={rss_before}, after={rss_after}, delta={rss_after - rss_before}")
        print(f"    {args.html_source}: before={html_before}, after={html_after}, delta={html_after - html_before}")

        total_items = db.query(SourceItem).count()
        total_fetch_runs = db.query(FetchRun).count()
        print(f"    Total SourceItem count: {total_items}")
        print(f"    Total FetchRun count:   {total_fetch_runs}")

        return rss_result, html_result, rss_before, rss_after, html_before, html_after

    finally:
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    # Handle --isolated-db BEFORE importing app.db
    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_probe_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    # Now import after env is set
    from app.db import SessionLocal, engine
    from app.models import FetchRun

    all_passed = True
    run_results = []

    for run_idx in range(1, args.repeat + 1):
        if args.repeat > 1:
            print(f"\n{'='*60}")
            print(f"RUN {run_idx}/{args.repeat}")
            print(f"{'='*60}")

        rss_res, html_res, rss_before, rss_after, html_before, html_after = _run_acceptance(args)
        run_results.append({
            "rss": rss_res,
            "html": html_res,
            "rss_before": rss_before,
            "rss_after": rss_after,
            "html_before": html_before,
            "html_after": html_after,
        })

    # --- Acceptance Summary ---
    print("\n" + "=" * 60)
    print("Acceptance Summary")
    print("=" * 60)

    passed = True

    # Check 1: At least one source had success or partial_failed
    rss_ok = run_results[0]["rss"] and run_results[0]["rss"]["status"] in ("success", "partial_failed")
    html_ok = run_results[0]["html"] and run_results[0]["html"]["status"] in ("success", "partial_failed")
    if not rss_ok and not html_ok:
        print("  [FAIL] Neither RSS nor HTML source succeeded or partial_failed")
        passed = False
    else:
        print("  [OK] At least one source succeeded or partial_failed")

    # Check 2: At least one source discovered new SourceItems on first run
    first = run_results[0]
    rss_got_new = (first["rss_after"] > first["rss_before"]) if first["rss"] else False
    html_got_new = (first["html_after"] > first["html_before"]) if first["html"] else False
    if not rss_got_new and not html_got_new:
        # Fallback: check if any items_updated > 0
        rss_updated = first["rss"]["items_updated"] > 0 if first["rss"] else False
        html_updated = first["html"]["items_updated"] > 0 if first["html"] else False
        if not rss_updated and not html_updated:
            print("  [FAIL] No new SourceItems discovered on first run and no items_updated")
            passed = False
        else:
            print("  [OK] No new items on first run (source already had items, updated)")
    else:
        if rss_got_new:
            print(f"  [OK] RSS discovered {first['rss_after'] - first['rss_before']} new SourceItems")
        if html_got_new:
            print(f"  [OK] HTML discovered {first['html_after'] - first['html_before']} new SourceItems")

    # Check 3: Idempotency (if repeat > 1)
    if args.repeat >= 2:
        second = run_results[1]
        second_rss_updated = second["rss"]["items_updated"] > 0 if second["rss"] else False
        second_html_updated = second["html"]["items_updated"] > 0 if second["html"] else False
        second_rss_new = (second["rss_after"] > second["rss_before"]) if second["rss"] else False
        second_html_new = (second["html_after"] > second["html_before"]) if second["html"] else False

        # No new items on second run (should only update)
        if second_rss_new or second_html_new:
            print(f"  [FAIL] Second run created new items (should only update): "
                  f"rss_new={second_rss_new}, html_new={second_html_new}")
            passed = False
        else:
            print(f"  [OK] Second run: no new items (rss_updated={second_rss_updated}, html_updated={second_html_updated})")
    else:
        # For single run, still check that we have some items
        total_after = first["rss_after"] + first["html_after"]
        if total_after < 1:
            print(f"  [FAIL] No SourceItems found after first run")
            passed = False
        else:
            print(f"  [OK] Total SourceItems after first run: {total_after}")

    # Check 4: Failed sources have error_message
    from app.db import SessionLocal
    db = SessionLocal()
    try:
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
    finally:
        db.close()

    # Cleanup isolated DB if not --keep-db
    if isolated_db_path and not args.keep_db:
        import sqlite3
        try:
            os.remove(isolated_db_path)
            print(f"\n[INFO] Cleaned up isolated DB: {isolated_db_path}")
        except OSError:
            print(f"\n[WARN] Could not remove isolated DB: {isolated_db_path}")

    print()
    if passed:
        print("[PASS] ACCEPTANCE PASSED")
        return 0
    else:
        print("[FAIL] ACCEPTANCE FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
