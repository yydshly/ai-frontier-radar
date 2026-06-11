#!/usr/bin/env python3
"""Diagnose data quality issues in the SourceItem / snapshot / summary pipeline.

Read-only diagnostics — no database writes, no file deletions.

Checks seven quality categories (V1.0-beta.15):
A. content_exists_but_snapshot_missing  — SourceItem has fetched/compiled status but no snapshot file
B. summary_exists_but_snapshot_missing  — item has zh_summary in raw_metadata_json but no snapshot file
C. source_item_without_url             — SourceItem has no URL
D. source_item_without_title           — SourceItem has no title
E. source_item_without_source          — SourceItem.source_id does not reference a real Source row
F. duplicate_url_items                 — duplicate URL within the same source
G. stale_failed_fetch_runs             — FetchRun with status=failed and [stale-timeout] marker

Each issue is tagged with a risk level and a recommended action.

Usage (dry-run, default):
    python scripts/diagnose_data_quality.py
    python scripts/diagnose_data_quality.py --source-key openai_news

Exit code: 0 always (this is a diagnostic, not a test).
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import SessionLocal, init_db
from app.models import Source, SourceItem, InsightCard, FetchRun
from app.application.content.content_snapshot import get_snapshot_path, load_snapshot


# ── Issue definitions ────────────────────────────────────────────────────────────
from dataclasses import dataclass, field


@dataclass
class IssueCategory:
    key: str
    label: str
    risk: str  # low / medium / high
    action: str
    count: int = 0
    samples: list[str] = field(default_factory=list)


def diagnose_database(db, source_key: str | None = None) -> list[IssueCategory]:
    """Diagnose all quality categories. Returns a list of IssueCategory.

    Args:
        db: SQLAlchemy session.
        source_key: if provided, categories A-E are scoped to that source_key only.
                    Category F (duplicates) is always full-scan.
                    Category G (stale fetch runs) is always full-scan.
    """
    categories = []

    # Base query scoped to source_key (used for A-E)
    def scoped_query(q):
        if source_key:
            return q.filter(SourceItem.source_key == source_key)
        return q

    # ── A. content_exists_but_snapshot_missing ─────────────────────
    print("[1/7] A. content_exists_but_snapshot_missing...")
    fetched_items = scoped_query(
        db.query(SourceItem).filter(SourceItem.status.in_(["fetched", "compiled"]))
    ).all()
    no_snapshot = [i for i in fetched_items if not get_snapshot_path(i.id).exists()]
    categories.append(IssueCategory(
        key="A",
        label="A. content_exists_but_snapshot_missing",
        risk="medium",
        action="Restore snapshot file or re-fetch content; blocks summary generation.",
        count=len(no_snapshot),
        samples=[
            f"  id={i.id} source_key={i.source_key}: "
            f"title={i.title[:40] if i.title else '(none)'}"
            for i in no_snapshot[:5]
        ]
    ))

    # ── B. summary_exists_but_snapshot_missing ────────────────────
    print("[2/7] B. summary_exists_but_snapshot_missing...")
    items_with_summary = []
    for item in scoped_query(
        db.query(SourceItem).filter(SourceItem.raw_metadata_json.isnot(None))
    ).all():
        try:
            meta = json.loads(item.raw_metadata_json)
            if meta.get("zh_summary") or meta.get("summary_zh"):
                items_with_summary.append(item)
        except Exception:
            pass
    missing_snap_for_summary = [
        i for i in items_with_summary if not get_snapshot_path(i.id).exists()
    ]
    categories.append(IssueCategory(
        key="B",
        label="B. summary_exists_but_snapshot_missing",
        risk="medium",
        action="Regenerate snapshot from raw_metadata_json or re-fetch source; summary exists but content inaccessible.",
        count=len(missing_snap_for_summary),
        samples=[
            f"  id={i.id} source_key={i.source_key}: "
            f"title={i.title[:40] if i.title else '(none)'}"
            for i in missing_snap_for_summary[:5]
        ]
    ))

    # ── C. source_item_without_url ───────────────────────────────
    print("[3/7] C. source_item_without_url...")
    no_url = scoped_query(
        db.query(SourceItem).filter(
            (SourceItem.url == None) | (SourceItem.url == "")
        )
    ).all()
    categories.append(IssueCategory(
        key="C",
        label="C. source_item_without_url",
        risk="high",
        action="Remove orphan items or backfill URL; no URL means no InsightCard can be generated.",
        count=len(no_url),
        samples=[
            f"  id={i.id} source_key={i.source_key}: "
            f"title={i.title[:40] if i.title else '(none)'}"
            for i in no_url[:5]
        ]
    ))

    # ── D. source_item_without_title ──────────────────────────────
    print("[4/7] D. source_item_without_title...")
    no_title = scoped_query(
        db.query(SourceItem).filter(
            (SourceItem.title == None) | (SourceItem.title == "")
        )
    ).all()
    categories.append(IssueCategory(
        key="D",
        label="D. source_item_without_title",
        risk="medium",
        action="Backfill title from metadata or remove; title is required for card display.",
        count=len(no_title),
        samples=[
            f"  id={i.id} source_key={i.source_key}: "
            f"url={i.url[:60] if i.url else '(none)'}"
            for i in no_title[:5]
        ]
    ))

    # ── E. source_item_without_source ─────────────────────────────
    print("[5/7] E. source_item_without_source (orphaned source_id)...")
    orphaned_source = []
    for item in scoped_query(
        db.query(SourceItem).filter(SourceItem.source_id.isnot(None))
    ).all():
        src = db.query(Source).filter(Source.id == item.source_id).first()
        if not src:
            orphaned_source.append(item)
    categories.append(IssueCategory(
        key="E",
        label="E. source_item_without_source",
        risk="high",
        action="Delete orphaned SourceItems or re-associate with correct source; these items are unreachable.",
        count=len(orphaned_source),
        samples=[
            f"  id={i.id} source_id={i.source_id}: "
            f"url={i.url[:60] if i.url else '(none)'}"
            for i in orphaned_source[:5]
        ]
    ))

    # ── F. duplicate_url_items ────────────────────────────────────
    print("[6/7] F. duplicate_url_items...")
    url_counts: dict[tuple, list[int]] = defaultdict(list)
    all_items = db.query(SourceItem).all()
    for item in all_items:
        if item.url:
            url_counts[(item.source_id, item.url)].append(item.id)
    dupes = {k: v for k, v in url_counts.items() if len(v) > 1}
    dupe_count = sum(len(v) - 1 for v in dupes.values())
    dupe_samples = []
    for (src_id, url), ids in list(dupes.items())[:5]:
        src = db.query(Source).filter(Source.id == src_id).first()
        src_key = src.source_key if src else f"source_id={src_id}"
        dupe_samples.append(f"  {src_key}: {url[:80]} (ids: {ids})")
    categories.append(IssueCategory(
        key="F",
        label="F. duplicate_url_items",
        risk="low",
        action="Deduplicate manually; duplicates inflate item counts and may cause redundant InsightCards.",
        count=dupe_count,
        samples=dupe_samples
    ))

    # ── G. stale_failed_fetch_runs ────────────────────────────────
    print("[7/7] G. stale_failed_fetch_runs...")
    stale_failed = db.query(FetchRun).filter(
        FetchRun.status == "failed",
        FetchRun.error_message.like("%[stale-timeout]%")
    ).all()
    categories.append(IssueCategory(
        key="G",
        label="G. stale_failed_fetch_runs",
        risk="low",
        action="Run: python scripts/mark_stale_fetch_runs_failed.py --apply to recover; "
               "these runs were stuck in 'running' and were auto-marked failed.",
        count=len(stale_failed),
        samples=[
            f"  run_id={r.id} source_key={r.source_key} "
            f"finished_at={r.finished_at.strftime('%Y-%m-%d %H:%M') if r.finished_at else '?'}"
            for r in stale_failed[:5]
        ]
    ))

    return categories


def format_diagnosis_report(categories: list[IssueCategory], total_items: int) -> str:
    """Format diagnosis categories into a structured report."""
    lines = []
    lines.append("=" * 70)
    lines.append("Data Quality Diagnosis  (V1.0-beta.15 — read-only, no writes)")
    lines.append("=" * 70)
    lines.append(f"Total SourceItems in database : {total_items}")
    lines.append("")

    RISK_ICON = {"low": "[LOW ]", "medium": "[MED ]", "high": "[HIGH]"}
    total_issues = 0

    for cat in categories:
        icon = RISK_ICON.get(cat.risk, "[????]")
        lines.append(f"{icon} {cat.label}: {cat.count}")
        if cat.samples:
            for s in cat.samples:
                lines.append(f"       {s}")
        lines.append(f"       → Risk: {cat.risk.upper()}  Action: {cat.action}")
        lines.append("")
        total_issues += cat.count

    lines.append("=" * 70)
    lines.append(f"Total issues : {total_issues}")
    lines.append("")
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
    args = parser.parse_args()

    print("=" * 70)
    print("Data Quality Diagnosis")
    print("=" * 70)

    init_db()
    db = SessionLocal()
    try:
        # Count total items for this source_key filter
        base_query = db.query(SourceItem)
        if args.source_key:
            base_query = base_query.filter(SourceItem.source_key == args.source_key)
        total_items = base_query.count()

        print(f"\n[OK] Scanning {total_items} SourceItem(s)"
              + (f" for source_key='{args.source_key}'" if args.source_key else ""))
        if args.source_key:
            print(f"    (categories A/B/C/D/E/F are filtered; G is always full-scan)")

        if total_items == 0 and not args.source_key:
            print("[INFO] No SourceItems found. Nothing to diagnose.")
            return 0

        categories = diagnose_database(db, args.source_key)
        report = format_diagnosis_report(categories, total_items)
        print()
        print(report)

        total_issues = sum(cat.count for cat in categories)
        print()
        if total_issues == 0:
            print("[OK] No data quality issues found.")
        else:
            print(f"[WARN] Found {total_issues} total quality issue(s).")
        print("=" * 70)
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
