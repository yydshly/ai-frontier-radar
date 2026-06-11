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
G. historical_stale_failed_fetch_runs — FetchRun with status=failed and [stale-timeout] marker (informational)

A–F are actionable issues that affect data quality.
G is informational: the records already carry the [stale-timeout] marker; no apply needed.

Each issue is tagged with a risk level and a recommended action.
For A and B, extended analysis shows by-source breakdown and recoverability.

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
    risk: str  # low / medium / high / info
    action: str
    count: int = 0
    samples: list[str] = field(default_factory=list)
    detail: str = ""  # extended info (e.g. by-source stats, recoverability)


def diagnose_database(db, source_key: str | None = None) -> tuple[list[IssueCategory], list[IssueCategory]]:
    """Diagnose all quality categories. Returns (actionable_categories, informational_categories).

    Args:
        db: SQLAlchemy session.
        source_key: if provided, categories A-E are scoped to that source_key only.
                    Category F (duplicates) is always full-scan.
                    Category G (stale fetch runs) is always full-scan.
    """
    actionable: list[IssueCategory] = []
    informational: list[IssueCategory] = []

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
    no_snapshot_A = [i for i in fetched_items if not get_snapshot_path(i.id).exists()]

    # Extended analysis for A
    a_by_source: dict[str, int] = defaultdict(int)
    a_with_url = sum(1 for i in no_snapshot_A if i.url and i.url.strip())
    a_with_title = sum(1 for i in no_snapshot_A if i.title and i.title.strip())
    a_with_summary = 0
    a_with_card = 0
    for i in no_snapshot_A:
        if i.raw_metadata_json:
            try:
                meta = json.loads(i.raw_metadata_json)
                if meta.get("zh_summary") or meta.get("summary_zh"):
                    a_with_summary += 1
            except Exception:
                pass
        if i.insight_card_id:
            a_with_card += 1
        a_by_source[i.source_key] += 1

    a_detail = _format_ab_detail("A", a_by_source, a_with_url, a_with_title, a_with_summary, a_with_card)

    actionable.append(IssueCategory(
        key="A",
        label="A. content_exists_but_snapshot_missing",
        risk="medium",
        action="Do not delete. Candidate for snapshot refetch or rebuild.",
        count=len(no_snapshot_A),
        samples=[
            f"  id={i.id} source_key={i.source_key}: "
            f"title={i.title[:40] if i.title else '(none)'}"
            for i in no_snapshot_A[:5]
        ],
        detail=a_detail,
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
    missing_snap_B = [
        i for i in items_with_summary if not get_snapshot_path(i.id).exists()
    ]

    # Extended analysis for B
    b_by_source: dict[str, int] = defaultdict(int)
    b_with_url = sum(1 for i in missing_snap_B if i.url and i.url.strip())
    b_with_title = sum(1 for i in missing_snap_B if i.title and i.title.strip())
    b_with_summary = len(missing_snap_B)  # by definition
    b_with_card = sum(1 for i in missing_snap_B if i.insight_card_id)
    for i in missing_snap_B:
        b_by_source[i.source_key] += 1

    b_detail = _format_ab_detail("B", b_by_source, b_with_url, b_with_title, b_with_summary, b_with_card)

    actionable.append(IssueCategory(
        key="B",
        label="B. summary_exists_but_snapshot_missing",
        risk="medium",
        action="Do not delete. Candidate for snapshot rebuild or refetch.",
        count=len(missing_snap_B),
        samples=[
            f"  id={i.id} source_key={i.source_key}: "
            f"title={i.title[:40] if i.title else '(none)'}"
            for i in missing_snap_B[:5]
        ],
        detail=b_detail,
    ))

    # ── C. source_item_without_url ─────────────────────────────
    print("[3/7] C. source_item_without_url...")
    no_url = scoped_query(
        db.query(SourceItem).filter(
            (SourceItem.url == None) | (SourceItem.url == "")
        )
    ).all()
    actionable.append(IssueCategory(
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
    actionable.append(IssueCategory(
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
    actionable.append(IssueCategory(
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
    all_items_for_dupes = db.query(SourceItem).all()
    for item in all_items_for_dupes:
        if item.url:
            url_counts[(item.source_id, item.url)].append(item.id)
    dupes = {k: v for k, v in url_counts.items() if len(v) > 1}
    dupe_count = sum(len(v) - 1 for v in dupes.values())
    dupe_samples = []
    for (src_id, url), ids in list(dupes.items())[:5]:
        src = db.query(Source).filter(Source.id == src_id).first()
        src_key = src.source_key if src else f"source_id={src_id}"
        dupe_samples.append(f"  {src_key}: {url[:80]} (ids: {ids})")
    actionable.append(IssueCategory(
        key="F",
        label="F. duplicate_url_items",
        risk="low",
        action="Deduplicate manually; duplicates inflate item counts and may cause redundant InsightCards.",
        count=dupe_count,
        samples=dupe_samples
    ))

    # ── G. historical_stale_failed_fetch_runs (informational) ──────
    print("[7/7] G. historical_stale_failed_fetch_runs...")
    stale_failed = db.query(FetchRun).filter(
        FetchRun.status == "failed",
        FetchRun.error_message.like("%[stale-timeout]%")
    ).all()
    informational.append(IssueCategory(
        key="G",
        label="G. historical_stale_failed_fetch_runs [INFO]",
        risk="info",
        action="Already marked failed + [stale-timeout]. No apply needed. "
               "UI should display these neutrally (not as dirty data).",
        count=len(stale_failed),
        samples=[
            f"  run_id={r.id} source_key={r.source_key} "
            f"finished_at={r.finished_at.strftime('%Y-%m-%d %H:%M') if r.finished_at else '?'}"
            for r in stale_failed[:5]
        ]
    ))

    return actionable, informational


def _format_ab_detail(
    label: str,
    by_source: dict[str, int],
    with_url: int,
    with_title: int,
    with_summary: int,
    with_card: int,
) -> str:
    """Format extended A/B detail string."""
    lines = []
    lines.append(f"  by_source:")
    for key, count in sorted(by_source.items(), key=lambda x: -x[1]):
        lines.append(f"    {key}: {count}")
    lines.append(f"  recoverability:")
    lines.append(f"    with_url:      {with_url}/{with_url}")
    lines.append(f"    with_title:    {with_title}/{with_url}")
    lines.append(f"    with_summary:  {with_summary}/{with_url}")
    lines.append(f"    with_card:     {with_card}/{with_url}")
    return "\n".join(lines)


def format_diagnosis_report(
    actionable: list[IssueCategory],
    informational: list[IssueCategory],
    total_items: int,
) -> str:
    """Format diagnosis categories into a structured report."""
    lines = []
    lines.append("=" * 70)
    lines.append("Data Quality Diagnosis  (V1.0-beta.15 — read-only, no writes)")
    lines.append("=" * 70)
    lines.append(f"Total SourceItems in database : {total_items}")
    lines.append("")

    RISK_ICON = {"low": "[LOW ]", "medium": "[MED ]", "high": "[HIGH]", "info": "[INFO]"}
    total_actionable = sum(cat.count for cat in actionable)

    # ── Actionable issues ───────────────────────────────────────────
    lines.append("## Actionable issues")
    lines.append("")
    for cat in actionable:
        icon = RISK_ICON.get(cat.risk, "[????]")
        lines.append(f"{icon} {cat.label}: {cat.count}")
        if cat.samples:
            for s in cat.samples:
                lines.append(f"       {s}")
        if cat.detail:
            for s in cat.detail.split("\n"):
                lines.append(f"       {s}")
        lines.append(f"       → Risk: {cat.risk.upper()}  Action: {cat.action}")
        lines.append("")

    # ── Informational ─────────────────────────────────────────────
    lines.append("## Informational")
    lines.append("")
    for cat in informational:
        icon = RISK_ICON.get(cat.risk, "[????]")
        lines.append(f"{icon} {cat.label}: {cat.count}")
        if cat.samples:
            for s in cat.samples:
                lines.append(f"       {s}")
        lines.append(f"       → Note: {cat.action}")
        lines.append("")

    lines.append("=" * 70)
    lines.append(f"Actionable issues : {total_actionable}")
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

        actionable, informational = diagnose_database(db, args.source_key)
        report = format_diagnosis_report(actionable, informational, total_items)
        print()
        print(report)

        total_actionable = sum(cat.count for cat in actionable)
        print()
        if total_actionable == 0:
            print("[OK] No actionable data quality issues found.")
        else:
            print(f"[WARN] Found {total_actionable} actionable quality issue(s).")
        print("=" * 70)
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
