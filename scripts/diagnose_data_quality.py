#!/usr/bin/env python3
"""Diagnose data quality issues in the SourceItem / snapshot / summary pipeline.

Read-only diagnostics — no database writes, no file deletions.

Checks:
- duplicate URLs within the same source
- source_items without title
- source_items without URL
- items with status suggesting content was fetched but no snapshot file exists
- snapshot files that exist but have empty text
- summary-related failure/disabled counts
- insight_card_id that points to a non-existent card

Usage (dry-run, default):
    python scripts/diagnose_data_quality.py
    python scripts/diagnose_data_quality.py --source-key openai_news

Exit code: 0 always (this is a diagnostic, not a test).
"""
import argparse
import os
import sys
from collections import defaultdict
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source, SourceItem, InsightCard
from app.application.content.content_snapshot import get_snapshot_path, load_snapshot


def diagnose_database(db) -> dict:
    """Diagnose database-level quality issues."""
    issues = {
        "duplicate_source_item_urls": 0,
        "duplicate_source_item_url_samples": [],
        "source_items_without_title": 0,
        "source_items_without_title_samples": [],
        "source_items_without_url": 0,
        "source_items_without_url_samples": [],
        "items_with_content_fetched_but_no_snapshot": 0,
        "items_with_content_fetched_but_no_snapshot_samples": [],
        "snapshot_exists_but_empty_text": 0,
        "snapshot_exists_but_empty_text_samples": [],
        "summary_failed_count": 0,
        "summary_disabled_count": 0,
        "summary_missing_snapshot_count": 0,
        "insight_card_id_missing_card_count": 0,
        "insight_card_id_missing_card_samples": [],
    }

    # ── 1. Duplicate URLs per source ────────────────────────────
    print("[1/9] Checking for duplicate source_item URLs...")
    url_counts: dict[tuple, list[int]] = defaultdict(list)
    all_items = db.query(SourceItem).all()
    for item in all_items:
        if item.url:
            url_counts[(item.source_id, item.url)].append(item.id)

    dupes = {k: v for k, v in url_counts.items() if len(v) > 1}
    issues["duplicate_source_item_urls"] = sum(len(v) - 1 for v in dupes.values())
    if dupes:
        # Sample: take first 5 duplicate URL groups
        for (src_id, url), ids in list(dupes.items())[:5]:
            src = db.query(Source).filter(Source.id == src_id).first()
            src_key = src.source_key if src else f"source_id={src_id}"
            issues["duplicate_source_item_url_samples"].append(
                f"  {src_key}: {url[:80]} (ids: {ids})"
            )

    # ── 2. Items without title ─────────────────────────────────
    print("[2/9] Checking for items without title...")
    no_title = db.query(SourceItem).filter(
        (SourceItem.title == None) | (SourceItem.title == "")
    ).all()
    issues["source_items_without_title"] = len(no_title)
    issues["source_items_without_title_samples"] = [
        f"  id={i.id} source_key={i.source_key}: url={i.url[:60] if i.url else '(none)'}"
        for i in no_title[:5]
    ]

    # ── 3. Items without URL ───────────────────────────────────
    print("[3/9] Checking for items without URL...")
    no_url = db.query(SourceItem).filter(
        (SourceItem.url == None) | (SourceItem.url == "")
    ).all()
    issues["source_items_without_url"] = len(no_url)
    issues["source_items_without_url_samples"] = [
        f"  id={i.id} source_key={i.source_key}: title={i.title[:40] if i.title else '(none)'}"
        for i in no_url[:5]
    ]

    # ── 4. Content fetched but no snapshot ─────────────────────
    # Items with status "fetched" or "compiled" that have no snapshot file
    print("[4/9] Checking for content fetched but missing snapshot...")
    fetched_items = db.query(SourceItem).filter(
        SourceItem.status.in_(["fetched", "compiled"])
    ).all()
    no_snapshot = []
    for item in fetched_items:
        if not get_snapshot_path(item.id).exists():
            no_snapshot.append(item)
    issues["items_with_content_fetched_but_no_snapshot"] = len(no_snapshot)
    issues["items_with_content_fetched_but_no_snapshot_samples"] = [
        f"  id={i.id} source_key={i.source_key}: title={i.title[:40] if i.title else '(none)'}"
        for i in no_snapshot[:5]
    ]

    # ── 5. Snapshot exists but empty text ──────────────────────
    print("[5/9] Checking for snapshots with empty text...")
    all_items_ids = [i.id for i in db.query(SourceItem.id).all()]
    empty_snapshots = []
    for item_id in all_items_ids:
        snap_path = get_snapshot_path(item_id)
        if snap_path.exists():
            snap = load_snapshot(item_id)
            if snap and snap.get("text") in ("", None):
                empty_snapshots.append(item_id)
    issues["snapshot_exists_but_empty_text"] = len(empty_snapshots)
    issues["snapshot_exists_but_empty_text_samples"] = [
        f"  source_item_id={sid}"
        for sid in empty_snapshots[:5]
    ]

    # ── 6. Summary failed count ─────────────────────────────────
    print("[6/9] Checking for summary failures...")
    # Items with status="failed" and error_message containing "summary"
    failed_items = db.query(SourceItem).filter(
        SourceItem.status == "failed"
    ).all()
    summary_failed = [
        i for i in failed_items
        if i.error_message and "summary" in i.error_message.lower()
    ]
    issues["summary_failed_count"] = len(summary_failed)

    # ── 7. Summary disabled count ──────────────────────────────
    print("[7/9] Checking for disabled summaries...")
    # Items with status="failed" and error_message containing "disabled"
    summary_disabled = [
        i for i in failed_items
        if i.error_message and "disabled" in i.error_message.lower()
    ]
    issues["summary_disabled_count"] = len(summary_disabled)

    # ── 8. Summary missing snapshot ────────────────────────────
    print("[8/9] Checking for summaries missing snapshots...")
    # Items that have zh_summary or summary_zh in raw_metadata_json but no snapshot
    items_with_summary = []
    for item in db.query(SourceItem).filter(
        SourceItem.raw_metadata_json.isnot(None)
    ).all():
        import json
        try:
            meta = json.loads(item.raw_metadata_json)
            if meta.get("zh_summary") or meta.get("summary_zh"):
                items_with_summary.append(item)
        except Exception:
            pass

    missing_snap_for_summary = []
    for item in items_with_summary:
        if not get_snapshot_path(item.id).exists():
            missing_snap_for_summary.append(item)
    issues["summary_missing_snapshot_count"] = len(missing_snap_for_summary)

    # ── 9. insight_card_id with missing card ───────────────────
    print("[9/9] Checking for orphaned insight_card_ids...")
    items_with_card_id = db.query(SourceItem).filter(
        SourceItem.insight_card_id.isnot(None)
    ).all()
    orphaned = []
    for item in items_with_card_id:
        card = db.query(InsightCard).filter(InsightCard.id == item.insight_card_id).first()
        if not card:
            orphaned.append(item)
    issues["insight_card_id_missing_card_count"] = len(orphaned)
    issues["insight_card_id_missing_card_samples"] = [
        f"  source_item.id={i.id} insight_card_id={i.insight_card_id}"
        for i in orphaned[:5]
    ]

    return issues


def format_diagnosis_report(issues: dict, total_items: int) -> str:
    """Format diagnosis issues into a readable report."""
    lines = []
    lines.append("-" * 60)
    lines.append("Data Quality Diagnosis Report")
    lines.append("-" * 60)
    lines.append(f"Total source_items in database: {total_items}")
    lines.append("")

    def report_count(key: str, label: str):
        count = issues.get(key, 0)
        icon = "[OK]" if count == 0 else "[WARN]"
        lines.append(f"{icon} {label}: {count}")
        samples_key = key + "_samples"
        if issues.get(samples_key):
            for s in issues[samples_key]:
                lines.append(f"     {s}")

    report_count("duplicate_source_item_urls", "duplicate URLs (within same source)")
    lines.append("")
    report_count("source_items_without_title", "items without title")
    lines.append("")
    report_count("source_items_without_url", "items without URL")
    lines.append("")
    report_count("items_with_content_fetched_but_no_snapshot", "items with content fetched but no snapshot file")
    lines.append("")
    report_count("snapshot_exists_but_empty_text", "snapshot files with empty text")
    lines.append("")
    report_count("summary_failed_count", "items with failed summary")
    lines.append("")
    report_count("summary_disabled_count", "items with disabled summary")
    lines.append("")
    report_count("summary_missing_snapshot_count", "summaries present but snapshot missing")
    lines.append("")
    report_count("insight_card_id_missing_card_count", "items with invalid insight_card_id")

    lines.append("")
    lines.append("-" * 60)
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose data quality issues in SourceItem pipeline. Read-only."
    )
    parser.add_argument(
        "--source-key",
        type=str, default=None,
        help="Filter diagnosis to a specific source_key."
    )
    parser.add_argument(
        "--limit",
        type=int, default=None,
        help="Limit number of items scanned (for performance on large DBs)."
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Data Quality Diagnosis")
    print("=" * 60)

    init_db()
    db = SessionLocal()
    try:
        # Base query
        base_query = db.query(SourceItem)
        if args.source_key:
            base_query = base_query.filter(SourceItem.source_key == args.source_key)

        total_items = base_query.count()
        print(f"\n[OK] Scanning {total_items} SourceItem(s)"
              + (f" for source_key='{args.source_key}'" if args.source_key else ""))

        if total_items == 0:
            print("[INFO] No SourceItems found. Nothing to diagnose.")
            return 0

        issues = diagnose_database(db)

        print()
        print(format_diagnosis_report(issues, total_items))

        # Summary
        error_count = sum([
            issues.get("duplicate_source_item_urls", 0),
            issues.get("source_items_without_title", 0),
            issues.get("source_items_without_url", 0),
            issues.get("items_with_content_fetched_but_no_snapshot", 0),
            issues.get("snapshot_exists_but_empty_text", 0),
            issues.get("summary_failed_count", 0),
            issues.get("summary_disabled_count", 0),
            issues.get("summary_missing_snapshot_count", 0),
            issues.get("insight_card_id_missing_card_count", 0),
        ])

        print()
        if error_count == 0:
            print("[OK] No data quality issues found.")
        else:
            print(f"[WARN] Found {error_count} total quality issue(s).")
        print("=" * 60)
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
