#!/usr/bin/env python3
"""Safe polluted data cleanup tool — V1.0-beta.15 Phase 2.

Safety model:
- Default mode is DRY-RUN: prints a cleanup plan, writes nothing.
- --apply flag is required to modify the database.
- Before applying, auto-backups SQLite DB to data/backups/.
- This script handles ONLY safe, reversible operations.

Allowed in safe_to_apply_now (auto-handled on --apply):
  1. stale running FetchRun → failed (with [stale-timeout] marker)
  2. stale failed FetchRun with [stale-timeout] → no-op (already marked)

Listed in manual_review_required (plan only, NOT auto-deleted):
  3. orphan SourceItem (source_id is None or references non-existent Source)
  4. SourceItem with empty url
  5. SourceItem with empty title AND empty url
  6. orphan InsightCard (card exists but no SourceItem links to it)

Listed in do_not_touch_in_phase_2 (plan only):
  A. snapshot_missing_items (61) — A + B from diagnose
  F. duplicate_url_items — would require dedup logic

Usage:
    python scripts/cleanup_polluted_data.py          # dry-run
    python scripts/cleanup_polluted_data.py --apply   # apply safe cleanup
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Backup helpers ────────────────────────────────────────────────────────────


def backup_sqlite_db(db_path: Path) -> Path:
    """Create a timestamped backup of a SQLite database file.

    Fails if db_path does not exist or backup already exists.
    Returns the backup Path.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"DB file not found: {db_path}")

    backups_dir = PROJECT_ROOT / "data" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"ai_frontier_radar_before_cleanup_{timestamp}.db"

    if backup_path.exists():
        raise RuntimeError(f"Backup already exists (race condition): {backup_path}")

    shutil.copy2(db_path, backup_path)
    return backup_path


# ── Cleanup plan dataclasses ─────────────────────────────────────────────────


class CleanupPlan:
    """Holds the results of analyzing the database."""

    def __init__(self):
        # safe_to_apply_now
        self.stale_running_count: int = 0
        self.stale_running_samples: list[str] = []

        # manual_review_required (listed only, not deleted)
        self.orphan_source_items_count: int = 0
        self.orphan_source_items_samples: list[str] = []
        self.items_without_url_count: int = 0
        self.items_without_url_samples: list[str] = []
        self.items_without_title_and_url_count: int = 0
        self.items_without_title_and_url_samples: list[str] = []
        self.orphan_insight_cards_count: int = 0
        self.orphan_insight_cards_samples: list[str] = []

        # do_not_touch_in_phase_2 (read from diagnose_data_quality.py)
        self.snapshot_missing_items_count: int = 0  # A: fetched/compiled no snapshot
        self.snapshot_missing_B_count: int = 0     # B: has zh_summary no snapshot
        self.duplicate_url_groups_count: int = 0


# ── Analysis ─────────────────────────────────────────────────────────────────


def analyze_database(db) -> CleanupPlan:
    """Analyze the database and return a CleanupPlan (read-only)."""
    plan = CleanupPlan()

    from app.models import FetchRun, SourceItem, Source, InsightCard
    from app.application.sources.stale_runs import (
        build_stale_fetch_run_report,
        get_stale_running_threshold_minutes,
    )
    from app.application.content.content_snapshot import get_snapshot_path
    import json

    # ── 1. stale running FetchRun ─────────────────────────────────
    try:
        threshold = get_stale_running_threshold_minutes()
    except Exception:
        threshold = 120  # fallback

    stale_report = build_stale_fetch_run_report(db, threshold_minutes=threshold)
    plan.stale_running_count = stale_report.stale_count
    plan.stale_running_samples = [
        f"  run_id={d.run_id} source_key={d.source_key} age_minutes={d.age_minutes}"
        for d in stale_report.stale_runs[:5]
    ]

    # ── 2. orphan SourceItem (source_id is None or Source doesn't exist) ──
    orphan_items: list[SourceItem] = []
    no_url_items: list[SourceItem] = []
    no_title_no_url_items: list[SourceItem] = []

    all_items = db.query(SourceItem).all()
    existing_source_ids = {s.id for s in db.query(Source.id).all()}

    for item in all_items:
        # Check orphan source
        if item.source_id is None or item.source_id not in existing_source_ids:
            orphan_items.append(item)
        # Check empty url
        if not (item.url and item.url.strip()):
            no_url_items.append(item)
        # Check empty title AND empty url
        if not (item.title and item.title.strip()) and not (item.url and item.url.strip()):
            no_title_no_url_items.append(item)

    plan.orphan_source_items_count = len(orphan_items)
    plan.orphan_source_items_samples = [
        f"  id={i.id} source_id={i.source_id} title={str(i.title or '')[:40]}"
        for i in orphan_items[:5]
    ]

    plan.items_without_url_count = len(no_url_items)
    plan.items_without_url_samples = [
        f"  id={i.id} source_key={i.source_key} title={str(i.title or '')[:40]}"
        for i in no_url_items[:5]
    ]

    plan.items_without_title_and_url_count = len(no_title_no_url_items)
    plan.items_without_title_and_url_samples = [
        f"  id={i.id} source_key={i.source_key}"
        for i in no_title_no_url_items[:5]
    ]

    # ── 3. orphan InsightCard ─────────────────────────────────────
    all_cards = db.query(InsightCard).all()
    linked_card_ids = {
        i.insight_card_id
        for i in db.query(SourceItem).filter(SourceItem.insight_card_id.isnot(None)).all()
    }
    orphan_cards = [c for c in all_cards if c.id not in linked_card_ids]
    plan.orphan_insight_cards_count = len(orphan_cards)
    plan.orphan_insight_cards_samples = [
        f"  card_id={c.id} title={str(c.source_title or '')[:40]}"
        for c in orphan_cards[:5]
    ]

    # ── 4. A/B snapshot missing items (from diagnose logic) ─────────
    # A: status=fetched/compiled but no snapshot
    fetched_items = db.query(SourceItem).filter(
        SourceItem.status.in_(["fetched", "compiled"])
    ).all()
    plan.snapshot_missing_items_count = sum(
        1 for i in fetched_items if not get_snapshot_path(i.id).exists()
    )
    # B: has zh_summary in raw_metadata_json but no snapshot
    items_with_summary = []
    for item in db.query(SourceItem).filter(SourceItem.raw_metadata_json.isnot(None)).all():
        try:
            meta = json.loads(item.raw_metadata_json)
            if meta.get("zh_summary") or meta.get("summary_zh"):
                items_with_summary.append(item)
        except Exception:
            pass
    plan.snapshot_missing_B_count = sum(
        1 for i in items_with_summary if not get_snapshot_path(i.id).exists()
    )

    # ── 5. duplicate URL groups ─────────────────────────────────────
    from collections import defaultdict
    url_counts: dict[tuple, list[int]] = defaultdict(list)
    for item in db.query(SourceItem).all():
        if item.url:
            url_counts[(item.source_id, item.url)].append(item.id)
    plan.duplicate_url_groups_count = sum(1 for v in url_counts.values() if len(v) > 1)

    return plan


def format_plan(plan: CleanupPlan, mode: str) -> str:
    """Format a CleanupPlan into a human-readable report."""
    lines = []
    lines.append("=" * 70)
    lines.append("AI Frontier Radar — polluted data cleanup plan")
    lines.append(f"Mode: {'APPLY' if mode == 'apply' else 'DRY-RUN'}")
    lines.append("=" * 70)
    lines.append("")

    # ── Section 1: safe_to_apply_now ──────────────────────────────
    lines.append("## safe_to_apply_now")
    lines.append("")
    lines.append(f"  would_reset_stale_running_fetch_runs: {plan.stale_running_count}")
    if plan.stale_running_samples:
        for s in plan.stale_running_samples:
            lines.append(f"    {s}")
    lines.append("")
    lines.append("  These are FetchRuns stuck in 'running' state for too long.")
    lines.append("  On --apply: status → failed, error_message gets [stale-timeout] marker.")
    lines.append("  No SourceItem or InsightCard rows are modified.")
    lines.append("")

    # ── Section 2: manual_review_required ─────────────────────────
    lines.append("## manual_review_required (listed only — NOT auto-deleted)")
    lines.append("")
    lines.append(f"  would_delete_source_items_without_url: {plan.items_without_url_count}")
    if plan.items_without_url_samples:
        for s in plan.items_without_url_samples:
            lines.append(f"    {s}")
    lines.append("")

    lines.append(f"  would_delete_source_items_without_source: {plan.orphan_source_items_count}")
    if plan.orphan_source_items_samples:
        for s in plan.orphan_source_items_samples:
            lines.append(f"    {s}")
    lines.append("")

    lines.append(
        f"  would_delete_source_items_without_title_and_url: "
        f"{plan.items_without_title_and_url_count}"
    )
    if plan.items_without_title_and_url_samples:
        for s in plan.items_without_title_and_url_samples:
            lines.append(f"    {s}")
    lines.append("")

    lines.append(f"  would_delete_orphan_insight_cards: {plan.orphan_insight_cards_count}")
    if plan.orphan_insight_cards_samples:
        for s in plan.orphan_insight_cards_samples:
            lines.append(f"    {s}")
    lines.append("")

    # ── Section 3: do_not_touch_in_phase_2 ───────────────────────
    lines.append("## do_not_touch_in_phase_2")
    lines.append("")
    lines.append(
        f"  snapshot_missing_items_A: {plan.snapshot_missing_items_count} "
        f"(status=fetched/compiled but no snapshot file)"
    )
    lines.append(
        f"  snapshot_missing_items_B: {plan.snapshot_missing_B_count} "
        f"(has zh_summary but no snapshot file)"
    )
    lines.append("  → blocks summary generation. Requires re-fetch or metadata rebuild.")
    lines.append("")
    lines.append(
        f"  duplicate_url_groups: {plan.duplicate_url_groups_count} "
        f"(F from diagnose)"
    )
    lines.append("  → duplicates in same source. Requires manual dedup review.")
    lines.append("")

    # ── Footer ───────────────────────────────────────────────────
    if mode == "dry-run":
        lines.append("No changes written. Pass --apply to execute safe cleanup.")
    else:
        lines.append("Backup was created before applying changes.")
    lines.append("=" * 70)

    return "\n".join(lines)


def apply_safe_cleanup(db) -> int:
    """Execute the safe cleanup operations. Returns number of FetchRuns updated."""
    from app.models import FetchRun
    from app.application.sources.stale_runs import (
        build_stale_fetch_run_report,
        get_stale_running_threshold_minutes,
    )

    now = datetime.utcnow()
    threshold = get_stale_running_threshold_minutes()
    stale_report = build_stale_fetch_run_report(db, now=now, threshold_minutes=threshold)

    updated = 0
    for decision in stale_report.stale_runs:
        run = db.query(FetchRun).filter(FetchRun.id == decision.run_id).first()
        if run is None:
            continue
        if run.status != "running":
            continue
        # Re-confirm still stale
        started_at = run.started_at
        if started_at is None:
            is_stale = True
            age_minutes = None
        else:
            age_minutes = int((now - started_at).total_seconds() // 60)
            is_stale = age_minutes > threshold

        if not is_stale:
            continue

        run.status = "failed"
        run.finished_at = now
        age_str = age_minutes if age_minutes is not None else "unknown"
        run.error_message = (
            f"[stale-timeout] Marked failed by cleanup_polluted_data.py after "
            f"{age_str} minutes running. threshold={threshold}."
        )
        run.updated_at = now
        updated += 1

    db.commit()
    return updated


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Safe polluted data cleanup tool (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually write to the database. Without this flag the script is dry-run.",
    )
    args = parser.parse_args()

    mode = "apply" if args.apply else "dry-run"

    print("Loading database...")
    try:
        from app.db import SessionLocal, init_db, engine
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    init_db()
    db = SessionLocal()

    try:
        # Check if using SQLite and DB file exists
        db_url = str(engine.url)
        is_sqlite = "sqlite" in db_url

        # For SQLite, check the DB file path exists before applying
        db_file_path: Path | None = None
        if is_sqlite:
            # Extract file path from sqlite URL
            database = engine.url.database  # e.g. ./data/ai_frontier_radar.db or /abs/path
            if database and database != ":memory:":
                db_file_path = (PROJECT_ROOT / database).resolve()

        # ── Dry-run or Apply ──────────────────────────────────────
        plan = analyze_database(db)
        print(format_plan(plan, mode))

        if mode == "dry-run":
            print()
            print("No database changes were made.")
            return 0

        # ── Apply path ────────────────────────────────────────────
        if is_sqlite and db_file_path is not None:
            print()
            print(f"[BACKUP] Backing up SQLite DB: {db_file_path}")
            try:
                backup_path = backup_sqlite_db(db_file_path)
                print(f"[BACKUP] Created: {backup_path}")
            except FileNotFoundError:
                print("[ERROR] SQLite DB file not found. Cannot apply cleanup without a backup.")
                return 1
            except RuntimeError as e:
                print(f"[ERROR] {e}")
                return 1

        print()
        print("[APPLY] Executing safe cleanup...")

        updated = apply_safe_cleanup(db)
        print(f"[APPLY] Updated {updated} stale running FetchRun(s) to failed.")
        print("[APPLY] Done. Manual review items were NOT deleted (as designed).")
        return 0

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Cleanup failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
