#!/usr/bin/env python3
"""V0.7 acceptance script for real high-value source coverage.

Validates that the system can discover real article SourceItems from
Anthropic News, DeepMind Blog, and Mistral AI — not just Hugging Face.

This script accesses external websites. It is NOT run as part of smoke_test.

Usage:
    python scripts/acceptance_real_source_coverage.py
    python scripts/acceptance_real_source_coverage.py --isolated-db
    python scripts/acceptance_real_source_coverage.py --keep-db
    python scripts/acceptance_real_source_coverage.py --timeout 15
    python scripts/acceptance_real_source_coverage.py --repeat 2
    python scripts/acceptance_real_source_coverage.py --source-key anthropic_news --source-key deepmind_blog
"""
import argparse
import os
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source, SourceItem, FetchRun
from sqlalchemy.orm import Session
from app.sources import sync_sources_config_to_db
from app.sources.html_index_probe import (
    run_html_index_probe_for_source,
    _is_index_or_listing_url,
)
from app.sources.rss_probe import probe_rss_source
from app.sources.quality import classify_source_item_url


def _build_arg_parser():
    parser = argparse.ArgumentParser(
        description="V0.7 real source coverage acceptance (probes external sites)."
    )
    parser.add_argument(
        "--isolated-db",
        action="store_true",
        help="Use an isolated SQLite DB.",
    )
    parser.add_argument(
        "--keep-db",
        action="store_true",
        help="Keep the isolated DB after run (default: delete it after).",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="HTTP request timeout in seconds (default: 15).",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=2,
        help="Number of probe runs to verify idempotency (default: 2).",
    )
    parser.add_argument(
        "--source-key",
        action="append",
        dest="source_keys",
        default=[],
        help="Source key to probe (can be repeated). Defaults to 3 high-value sources.",
    )
    return parser


def _get_default_source_keys():
    return ["anthropic_news", "deepmind_blog", "mistral_ai_news"]


def _classify_source_items(db: Session, source: Source):
    """Classify existing SourceItems for a source using content quality rules.

    Returns (article_like_count, expected_content_count, suspected_listing_count,
             suspected_off_topic_count, article_samples, expected_samples,
             off_topic_samples).
    """
    items = db.query(SourceItem).filter(SourceItem.source_id == source.id).all()
    article_like = []
    expected_content = []
    suspected_listing = []
    suspected_off_topic = []

    for item in items:
        classification = classify_source_item_url(
            source.source_key, item.url, source.homepage_url or None
        )
        if classification["suspected_listing"]:
            suspected_listing.append(item)
        elif classification["expected_content"]:
            article_like.append(item)
            expected_content.append(item)
        else:
            # Not listing, not expected content = off-topic
            article_like.append(item)
            suspected_off_topic.append(item)

    return (
        len(article_like),
        len(expected_content),
        len(suspected_listing),
        len(suspected_off_topic),
        article_like[:5],
        expected_content[:5],
        suspected_off_topic[:5],
    )


def _print_source_result(
    source_key: str,
    fetch_strategy: str,
    status: str,
    items_found: int,
    items_new: int,
    items_updated: int,
    items_failed: int,
    error_message: str | None,
    article_like_count: int,
    expected_content_count: int,
    suspected_listing_count: int,
    suspected_off_topic_count: int,
    article_samples: list[SourceItem],
    expected_samples: list[SourceItem],
    off_topic_samples: list[SourceItem],
    db: Session,
):
    print(f"\n{'─' * 55}")
    print(f"  {source_key}  [{fetch_strategy}]")
    print(f"  status: {status}")
    print(f"  items_found={items_found}, new={items_new}, updated={items_updated}, failed={items_failed}")
    if error_message:
        print(f"  error: {error_message}")
    print(f"  article_like={article_like_count}, expected_content={expected_content_count}, "
          f"suspected_listing={suspected_listing_count}, suspected_off_topic={suspected_off_topic_count}")
    if suspected_listing_count > 0:
        print(f"  [!] WARNING: {suspected_listing_count} URL(s) may be listing/pagination pages")
    if suspected_off_topic_count > 0:
        print(f"  [!] WARNING: {suspected_off_topic_count} URL(s) are off-topic for this source")
    if expected_samples:
        print(f"  Top expected SourceItems:")
        for item in expected_samples:
            title = (item.title or "(无标题)")[:60]
            print(f"    - {title}")
            print(f"      {item.url[:80]}")
    elif article_samples:
        print(f"  Top discovered SourceItems (non-listing):")
        for item in article_samples:
            title = (item.title or "(无标题)")[:60]
            print(f"    - {title}")
            print(f"      {item.url[:80]}")
    return status in ("success", "partial_failed") and expected_content_count >= 1


def _run_probe_for_source(db: Session, source: Source, timeout: int, run_num: int):
    """Run probe and return FetchRun result."""
    if source.fetch_strategy == "html_index":
        fetch_run = run_html_index_probe_for_source(db, source, timeout_seconds=timeout)
    elif source.fetch_strategy == "rss":
        # RSS probe doesn't use FetchRun wrapper; we create one manually
        probe_result = probe_rss_source(db, source, timeout_seconds=timeout)

        fetch_run = FetchRun(
            source_id=source.id,
            source_key=source.source_key,
            run_type="manual",
            status="success" if not probe_result["error_message"] else "failed",
            started_at=datetime.utcnow(),
            finished_at=datetime.utcnow(),
            items_found=probe_result["items_found"],
            items_new=probe_result["items_new"],
            items_updated=probe_result["items_updated"],
            items_failed=probe_result["items_failed"],
            error_message=probe_result["error_message"],
        )
        db.add(fetch_run)
        db.commit()
        db.refresh(fetch_run)
    else:
        fetch_run = None
    return fetch_run


def _run_acceptance(args):
    print("=" * 60)
    print("V0.7 Real Source Coverage Acceptance")
    print("=" * 60)
    print("\n[!] NOTE: This script accesses external websites.")
    print("  Networks: anthropic.com, deepmind.google\n")

    init_db()
    print("[OK] Database initialized")

    db = SessionLocal()
    try:
        # Sync sources config
        print("\n[1] Syncing source config to database...")
        sync_result = sync_sources_config_to_db(db, force_reload=True)
        print(f"    total={sync_result['total']}, created={sync_result['created']}, "
              f"updated={sync_result['updated']}")

        # Determine source keys to probe
        source_keys = args.source_keys if args.source_keys else _get_default_source_keys()
        print(f"\n[2] Target sources: {source_keys}")

        # Load sources from DB
        sources = []
        for key in source_keys:
            src = db.query(Source).filter(Source.source_key == key).first()
            if not src:
                print(f"\n[WARN] Source '{key}' not found in registry — skipping")
                continue
            if not src.enabled:
                print(f"\n[WARN] Source '{key}' is disabled — skipping")
                continue
            sources.append(src)

        if not sources:
            print("\n[FAIL] No valid sources to probe.")
            return False

        # ── Run probes (repeat times) ──────────────────────────────────
        all_results = []

        for run_num in range(1, args.repeat + 1):
            print(f"\n{'═' * 60}")
            print(f"  Run {run_num}/{args.repeat}")
            print(f"{'═' * 60}")

            for source in sources:
                print(f"\n  Probing {source.source_key} ({source.fetch_strategy})...")
                try:
                    fetch_run = _run_probe_for_source(db, source, args.timeout, run_num)
                    (article_like, expected_content, suspected_listing,
                     suspected_off_topic, art_samples, exp_samples,
                     off_topic_samples) = _classify_source_items(db, source)

                    result = {
                        "source_key": source.source_key,
                        "fetch_strategy": source.fetch_strategy,
                        "run": run_num,
                        "status": fetch_run.status if fetch_run else "unsupported",
                        "items_found": fetch_run.items_found if fetch_run else 0,
                        "items_new": fetch_run.items_new if fetch_run else 0,
                        "items_updated": fetch_run.items_updated if fetch_run else 0,
                        "items_failed": fetch_run.items_failed if fetch_run else 0,
                        "error_message": fetch_run.error_message if fetch_run else "unsupported strategy",
                        "article_like_count": article_like,
                        "expected_content_count": expected_content,
                        "suspected_listing_count": suspected_listing,
                        "suspected_off_topic_count": suspected_off_topic,
                        "article_samples": art_samples,
                        "expected_samples": exp_samples,
                    }
                    all_results.append(result)

                    passed = _print_source_result(
                        source.source_key,
                        source.fetch_strategy,
                        fetch_run.status if fetch_run else "unsupported",
                        fetch_run.items_found if fetch_run else 0,
                        fetch_run.items_new if fetch_run else 0,
                        fetch_run.items_updated if fetch_run else 0,
                        fetch_run.items_failed if fetch_run else 0,
                        fetch_run.error_message if fetch_run else None,
                        article_like,
                        expected_content,
                        suspected_listing,
                        suspected_off_topic,
                        art_samples,
                        exp_samples,
                        off_topic_samples,
                        db,
                    )
                    print(f"  -> {'PASS' if passed else 'FAIL'}")

                except Exception as e:
                    print(f"  -> ERROR: {e}")
                    all_results.append({
                        "source_key": source.source_key,
                        "run": run_num,
                        "status": "exception",
                        "error_message": str(e),
                        "article_like_count": 0,
                        "expected_content_count": 0,
                        "suspected_listing_count": 0,
                        "suspected_off_topic_count": 0,
                    })

        # ── Summary ──────────────────────────────────────────────────────
        print(f"\n{'═' * 60}")
        print("  Acceptance Summary")
        print(f"{'═' * 60}")

        successful_sources = set()
        expected_content_sources = set()
        constraint_errors = []

        for r in all_results:
            if r["status"] in ("success", "partial_failed"):
                successful_sources.add(r["source_key"])
            if r["expected_content_count"] >= 1:
                expected_content_sources.add(r["source_key"])

        # Check for unique constraint errors
        for r in all_results:
            if "UNIQUE constraint" in str(r.get("error_message", "")):
                constraint_errors.append(r["source_key"])

        print(f"  Sources with successful probe: {len(successful_sources)}")
        print(f"  Sources with expected_content items: {len(expected_content_sources)}")
        print(f"  Unique constraint errors: {len(constraint_errors)}")

        # Determine pass/fail
        passed = True
        reasons = []

        if len(successful_sources) < 2:
            passed = False
            reasons.append(f"Only {len(successful_sources)} source(s) completed probe (need ≥2)")

        if len(expected_content_sources) < 2:
            passed = False
            reasons.append(f"Only {len(expected_content_sources)} source(s) produced expected_content SourceItems (need ≥2)")

        if constraint_errors:
            passed = False
            reasons.append(f"Unique constraint errors in: {constraint_errors}")

        # Warn about suspected listing pages and off-topic items
        for r in all_results:
            if r["suspected_listing_count"] > 0:
                print(f"  [!] WARNING: {r['source_key']} has {r['suspected_listing_count']} "
                      f"suspected listing/pagination URL(s)")
            if r["suspected_off_topic_count"] > 0:
                print(f"  [!] WARNING: {r['source_key']} has {r['suspected_off_topic_count']} "
                      f"off-topic URL(s)")

        print(f"\n  -> Overall: {'PASS' if passed else 'FAIL'}")
        for reason in reasons:
            print(f"     {reason}")

        return passed

    finally:
        db.close()


def main():
    parser = _build_arg_parser()
    args = parser.parse_args()

    isolated_db_path = None
    if args.isolated_db:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        db_name = f"acceptance_v07_{timestamp}.db"
        isolated_db_path = os.path.join("data", db_name)
        os.makedirs("data", exist_ok=True)
        os.environ["DATABASE_URL"] = f"sqlite:///{os.path.abspath(isolated_db_path)}"
        print(f"[INFO] Using isolated DB: {isolated_db_path}")

    try:
        result = _run_acceptance(args)
    finally:
        if isolated_db_path and not args.keep_db:
            try:
                if os.path.exists(isolated_db_path):
                    os.remove(isolated_db_path)
                print(f"\n[INFO] Cleaned up isolated DB: {isolated_db_path}")
            except OSError as e:
                print(f"\n[WARN] Could not remove isolated DB: {isolated_db_path}: {e}")

    print()
    if result:
        print("[PASS] ACCEPTANCE PASSED")
        return 0
    else:
        print("[FAIL] ACCEPTANCE FAILED")
        return 1


if __name__ == "__main__":
    sys.exit(main())
