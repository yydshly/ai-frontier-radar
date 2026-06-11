#!/usr/bin/env python3
"""Safe polluted data cleanup tool — V1.0-beta.15 Phase 4.

Safety model:
- Default mode is DRY-RUN: prints a cleanup plan, writes nothing.
- --apply flag is required to modify the database.
- --apply --delete-safe-snapshot-gaps is required to delete B-class snapshot gap candidates (48h protection).
- --apply --delete-b-without-card-now is for establishing a clean detection environment;
  removes B-class without InsightCard without 48h protection.
- Before applying, auto-backups SQLite DB to data/backups/.
- This script handles ONLY safe, reversible operations.

Allowed in safe_to_apply_now (auto-handled on --apply --delete-safe-snapshot-gaps):
  1. stale running FetchRun → failed (with [stale-timeout] marker)
  2. B-class snapshot gap safe-delete candidates (48h protection)

Allowed on --apply --delete-b-without-card-now:
  3. B-class without InsightCard, no 48h protection (for clean detection environment)

Listed in manual_review_required (plan only, NOT auto-deleted):
  4. orphan SourceItem (source_id is None or references non-existent Source)
  5. SourceItem with empty url
  6. SourceItem with empty title AND empty url
  7. orphan InsightCard (card exists but no SourceItem links to it)

Listed in do_not_touch_in_phase_2 (plan only):
  A. snapshot_missing_items — A-class, ALL protected (with_card)
  F. duplicate_url_items — would require dedup logic

B-class safe-delete candidate criteria (--delete-safe-snapshot-gaps, ALL must be true):
  - Belongs to B-class (has zh_summary in raw_metadata_json but no snapshot)
  - snapshot file is actually missing
  - raw_metadata_json has zh_summary or summary_zh
  - url is non-empty
  - title is non-empty
  - source_id can join to a real Source
  - Source.enabled = True
  - insight_card_id is NULL (no linked InsightCard)
  - first_seen_at AND last_seen_at are both older than 48 hours

B without card now criteria (--delete-b-without-card-now, ALL must be true):
  - Belongs to B-class (has zh_summary in raw_metadata_json but no snapshot)
  - snapshot file is actually missing
  - insight_card_id is NULL
  - url is non-empty
  - title is non-empty
  - source_id can join to a real Source
  - Source.enabled = True
  (no 48h requirement — for clean detection environment)

Usage:
    python scripts/cleanup_polluted_data.py                                    # dry-run
    python scripts/cleanup_polluted_data.py --apply                            # apply safe cleanup (FetchRun only)
    python scripts/cleanup_polluted_data.py --apply --delete-safe-snapshot-gaps # delete 48h-protected B-class
    python scripts/cleanup_polluted_data.py --apply --delete-b-without-card-now # delete all B without card
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Constants ─────────────────────────────────────────────────────────────────

SNAPSHOT_GAP_AGE_HOURS = 48


# ── Backup helpers ────────────────────────────────────────────────────────────


def backup_sqlite_db(db_path: Path, suffix: str = "cleanup") -> Path:
    """Create a timestamped backup of a SQLite database file.

    Fails if db_path does not exist or backup already exists.
    Returns the backup Path.
    """
    if not db_path.exists():
        raise FileNotFoundError(f"DB file not found: {db_path}")

    backups_dir = PROJECT_ROOT / "data" / "backups"
    backups_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backups_dir / f"ai_frontier_radar_before_{suffix}_{timestamp}.db"

    if backup_path.exists():
        raise RuntimeError(f"Backup already exists (race condition): {backup_path}")

    shutil.copy2(db_path, backup_path)
    return backup_path


# ── Cleanup plan dataclasses ─────────────────────────────────────────────────


@dataclass
class SnapshotGapCandidate:
    """A single B-class snapshot gap safe-delete candidate (48h protected)."""
    source_item_id: int
    source_key: str
    url: str
    title: str
    insight_card_id: int | None
    first_seen_at: datetime
    last_seen_at: datetime
    reason: str


@dataclass
class BWithoutCardCandidate:
    """A B-class SourceItem with no InsightCard — for clean detection environment."""
    source_item_id: int
    source_key: str
    url: str
    title: str
    insight_card_id: int | None
    first_seen_at: datetime
    last_seen_at: datetime
    reason: str


@dataclass
class CleanupPlan:
    """Holds the results of analyzing the database."""
    # snapshot_gap_cleanup_candidates
    b_safe_delete_candidates: list[SnapshotGapCandidate] = field(default_factory=list)
    b_without_card_candidates: list[BWithoutCardCandidate] = field(default_factory=list)

    # protected categories
    protected_a_with_card: int = 0       # A-class with insight_card_id
    protected_a_without_card: int = 0    # A-class without insight_card_id
    protected_b_with_card: int = 0       # B-class with insight_card_id
    protected_recent_items: int = 0     # B-class older than 48h but recent
    protected_invalid_metadata: int = 0  # B-class with invalid metadata

    # safe_to_apply_now
    stale_running_count: int = 0
    stale_running_samples: list[str] = field(default_factory=list)

    # manual_review_required (listed only, not deleted)
    orphan_source_items_count: int = 0
    orphan_source_items_samples: list[str] = field(default_factory=list)
    items_without_url_count: int = 0
    items_without_url_samples: list[str] = field(default_factory=list)
    items_without_title_and_url_count: int = 0
    items_without_title_and_url_samples: list[str] = field(default_factory=list)
    orphan_insight_cards_count: int = 0
    orphan_insight_cards_samples: list[str] = field(default_factory=list)

    # do_not_touch_in_phase_2 (read from diagnose_data_quality.py)
    snapshot_missing_items_count: int = 0  # A: fetched/compiled no snapshot
    snapshot_missing_B_count: int = 0      # B: has zh_summary no snapshot
    duplicate_url_groups_count: int = 0

    # filtered_from_ui (informational)
    ui_disabled_source_count: int = 0
    ui_missing_url_count: int = 0
    ui_missing_title_count: int = 0
    ui_orphan_source_count: int = 0

    # informational
    stale_failed_count: int = 0
    stale_failed_samples: list[str] = field(default_factory=list)


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
    import json as json_module

    cutoff = datetime.utcnow() - timedelta(hours=SNAPSHOT_GAP_AGE_HOURS)

    # ── 0. A/B snapshot gap analysis ─────────────────────────────────────────
    # A: status=fetched/compiled but no snapshot
    fetched_items = db.query(SourceItem).filter(
        SourceItem.status.in_(["fetched", "compiled"])
    ).all()
    no_snapshot_A = [i for i in fetched_items if not get_snapshot_path(i.id).exists()]
    plan.snapshot_missing_items_count = len(no_snapshot_A)

    # A-class protection level
    plan.protected_a_with_card = sum(1 for i in no_snapshot_A if i.insight_card_id)
    plan.protected_a_without_card = sum(1 for i in no_snapshot_A if not i.insight_card_id)

    # B: has zh_summary in raw_metadata_json but no snapshot
    items_with_summary: list[SourceItem] = []
    for item in db.query(SourceItem).filter(SourceItem.raw_metadata_json.isnot(None)).all():
        try:
            meta = json_module.loads(item.raw_metadata_json)
            if meta.get("zh_summary") or meta.get("summary_zh"):
                items_with_summary.append(item)
        except Exception:
            pass
    missing_snap_B = [
        i for i in items_with_summary if not get_snapshot_path(i.id).exists()
    ]
    plan.snapshot_missing_B_count = len(missing_snap_B)

    # B-class protection level
    plan.protected_b_with_card = sum(1 for i in missing_snap_B if i.insight_card_id)

    # Build valid source lookup
    valid_sources = {s.id: s for s in db.query(Source).filter(Source.enabled.is_(True)).all()}

    # Scan B-class items and classify into candidates vs protected
    b_candidates: list[SnapshotGapCandidate] = []
    recent_items = 0
    invalid_metadata_count = 0

    for item in missing_snap_B:
        # Skip A-class items
        if item.status in ("fetched", "compiled"):
            continue  # A-class — skip

        # Must have zh_summary in metadata (already filtered above, but re-verify)
        raw_meta = item.raw_metadata_json
        has_zh_summary = False
        if raw_meta:
            try:
                meta = json_module.loads(raw_meta)
                has_zh_summary = bool(meta.get("zh_summary") or meta.get("summary_zh"))
            except Exception:
                has_zh_summary = False

        if not has_zh_summary:
            invalid_metadata_count += 1
            continue

        # Must have url and title
        if not (item.url and item.url.strip()):
            invalid_metadata_count += 1
            continue
        if not (item.title and item.title.strip()):
            invalid_metadata_count += 1
            continue

        # Must have valid source
        if item.source_id not in valid_sources:
            invalid_metadata_count += 1
            continue

        # Must NOT have insight_card_id (protected)
        if item.insight_card_id:
            continue  # protected — B with card

        # Must be older than 48 hours (both first_seen_at AND last_seen_at)
        if item.first_seen_at and item.first_seen_at > cutoff:
            recent_items += 1
            continue
        if item.last_seen_at and item.last_seen_at > cutoff:
            recent_items += 1
            continue

        # All criteria met — safe to delete
        b_candidates.append(SnapshotGapCandidate(
            source_item_id=item.id,
            source_key=item.source_key,
            url=item.url or "",
            title=item.title or "",
            insight_card_id=item.insight_card_id,
            first_seen_at=item.first_seen_at or datetime.utcnow(),
            last_seen_at=item.last_seen_at or datetime.utcnow(),
            reason="b_snapshot_missing_no_card_older_than_48h",
        ))

    plan.b_safe_delete_candidates = b_candidates
    plan.protected_recent_items = recent_items
    plan.protected_invalid_metadata = invalid_metadata_count

    # ── 0b. B-class without InsightCard (no 48h requirement) ───────────────────
    # These are B-class items with no linked InsightCard that can be removed
    # to establish a clean detection environment. They may or may not be old.
    b_without_card: list[BWithoutCardCandidate] = []
    for item in missing_snap_B:
        # Already filtered: has zh_summary, no snapshot, not A-class
        # Must have no insight_card_id
        if item.insight_card_id:
            continue  # protected — B with card
        # Must have url and title
        if not (item.url and item.url.strip()):
            continue
        if not (item.title and item.title.strip()):
            continue
        # Must have valid source
        if item.source_id not in valid_sources:
            continue

        b_without_card.append(BWithoutCardCandidate(
            source_item_id=item.id,
            source_key=item.source_key,
            url=item.url or "",
            title=item.title or "",
            insight_card_id=item.insight_card_id,
            first_seen_at=item.first_seen_at or datetime.utcnow(),
            last_seen_at=item.last_seen_at or datetime.utcnow(),
            reason="b_without_card_for_clean_detection",
        ))

    plan.b_without_card_candidates = b_without_card

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

    # ── filtered_from_ui: counts matching the today radar guard (mutually exclusive) ──
    enabled_source_ids = {s.id for s in db.query(Source).filter(Source.enabled.is_(True)).all()}
    orphan_ui = 0
    disabled_ui = 0
    no_url_ui = 0
    no_title_ui = 0

    for item in all_items:
        # Priority 1: orphan source
        if item.source_id is None or item.source_id not in existing_source_ids:
            orphan_ui += 1
            continue
        # Priority 2: disabled source
        if item.source_id not in enabled_source_ids:
            disabled_ui += 1
            continue
        # Priority 3: missing url
        if not (item.url and item.url.strip()):
            no_url_ui += 1
            continue
        # Priority 4: missing title
        if not (item.title and item.title.strip()):
            no_title_ui += 1
            continue

    plan.ui_orphan_source_count = orphan_ui
    plan.ui_disabled_source_count = disabled_ui
    plan.ui_missing_url_count = no_url_ui
    plan.ui_missing_title_count = no_title_ui

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

    # ── G. historical stale failed fetch runs (informational) ─────────
    stale_failed_runs = db.query(FetchRun).filter(
        FetchRun.status == "failed",
        FetchRun.error_message.like("%[stale-timeout]%")
    ).all()
    plan.stale_failed_count = len(stale_failed_runs)
    plan.stale_failed_samples = [
        f"  run_id={r.id} source_key={r.source_key} "
        f"finished_at={r.finished_at.strftime('%Y-%m-%d %H:%M') if r.finished_at else '?'}"
        for r in stale_failed_runs[:5]
    ]

    # ── 4. duplicate URL groups ─────────────────────────────────────
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
    lines.append(f"Snapshot-gap safe-delete age threshold: {SNAPSHOT_GAP_AGE_HOURS} hours")
    lines.append("=" * 70)
    lines.append("")

    # ── Section 0: snapshot_gap_cleanup_candidates ─────────────────────
    lines.append("## snapshot_gap_cleanup_candidates")
    lines.append(f"  b_safe_delete_candidates: {len(plan.b_safe_delete_candidates)}")
    lines.append(f"  protected_a_with_card: {plan.protected_a_with_card}")
    lines.append(f"  protected_a_without_card: {plan.protected_a_without_card}")
    lines.append(f"  protected_b_with_card: {plan.protected_b_with_card}")
    lines.append(f"  protected_recent_items: {plan.protected_recent_items}")
    lines.append(f"  protected_invalid_metadata: {plan.protected_invalid_metadata}")
    lines.append("")

    if plan.b_safe_delete_candidates:
        lines.append("  B-class safe-delete candidate samples (up to 5):")
        for c in plan.b_safe_delete_candidates[:5]:
            lines.append(f"    id={c.source_item_id} source_key={c.source_key}")
            lines.append(f"      title={c.title[:50]} url={c.url[:60]}")
            lines.append(f"      first_seen_at={_fmt_dt(c.first_seen_at)} "
                         f"last_seen_at={_fmt_dt(c.last_seen_at)} "
                         f"insight_card_id={c.insight_card_id}")
            lines.append(f"      reason={c.reason}")
    lines.append("")

    # ── Section 0b: B-class without card (clean detection environment) ─────
    lines.append("## b_without_card_candidates")
    lines.append(f"  count: {len(plan.b_without_card_candidates)}")
    lines.append("  (B-class without InsightCard — eligible for --delete-b-without-card-now)")
    if plan.b_without_card_candidates:
        lines.append("  Samples (up to 5):")
        for c in plan.b_without_card_candidates[:5]:
            lines.append(f"    id={c.source_item_id} source_key={c.source_key}")
            lines.append(f"      title={c.title[:50]} url={c.url[:60]}")
            lines.append(f"      first_seen_at={_fmt_dt(c.first_seen_at)} "
                         f"last_seen_at={_fmt_dt(c.last_seen_at)} "
                         f"insight_card_id={c.insight_card_id}")
            lines.append(f"      reason={c.reason}")
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

    # ── Section 1b: filtered_from_ui ─────────────────────────────────
    total_ui_filtered = (
        plan.ui_orphan_source_count
        + plan.ui_disabled_source_count
        + plan.ui_missing_url_count
        + plan.ui_missing_title_count
    )
    lines.append("## filtered_from_ui")
    lines.append("  (these items are already hidden from today radar by quality guards)")
    lines.append(f"  total_filtered_from_ui: {total_ui_filtered}")
    lines.append(f"    orphan_source:     {plan.ui_orphan_source_count}")
    lines.append(f"    disabled_source:  {plan.ui_disabled_source_count}")
    lines.append(f"    missing_url:      {plan.ui_missing_url_count}")
    lines.append(f"    missing_title:    {plan.ui_missing_title_count}")
    lines.append("  Deleting these would have no visible effect on today radar.")
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
    lines.append(
        f"  Note: A-class with_card={plan.protected_a_with_card} — ALL protected"
    )
    lines.append(
        f"  Note: B-class with_card={plan.protected_b_with_card} — protected, not deleted"
    )
    lines.append("  → blocks summary generation. Requires re-fetch or metadata rebuild.")
    lines.append("")
    lines.append(
        f"  duplicate_url_groups: {plan.duplicate_url_groups_count} "
        f"(F from diagnose)"
    )
    lines.append("  → duplicates in same source. Requires manual dedup review.")
    lines.append("")

    # ── Section 4: informational ─────────────────────────────────
    lines.append("## informational")
    lines.append("")
    lines.append(f"  historical_stale_failed_fetch_runs: {plan.stale_failed_count}")
    if plan.stale_failed_samples:
        for s in plan.stale_failed_samples:
            lines.append(f"    {s}")
    lines.append("  → Already marked failed + [stale-timeout]. No apply needed.")
    lines.append("")

    # ── Footer ───────────────────────────────────────────────────
    if mode == "dry-run":
        lines.append("No changes written. Pass --apply to execute safe cleanup.")
        lines.append("Pass --apply --delete-safe-snapshot-gaps to also delete B-class candidates.")
    else:
        lines.append("Backup was created before applying changes.")
    lines.append("=" * 70)

    return "\n".join(lines)


def _fmt_dt(dt: datetime | None) -> str:
    """Format datetime safely."""
    if dt is None:
        return "None"
    return dt.strftime("%Y-%m-%d %H:%M")


# ── Audit export ───────────────────────────────────────────────────────────────


def export_audit(
    plan: CleanupPlan,
    mode: str,
    deleted_count: int = 0,
    backup_path: Path | None = None,
) -> Path:
    """Export cleanup audit to a JSONL file. Returns the export path."""
    exports_dir = PROJECT_ROOT / "data" / "cleanup_exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"cleanup_plan_{timestamp}.jsonl"
    export_path = exports_dir / filename

    with open(export_path, "w", encoding="utf-8") as f:
        # Write plan metadata
        meta = {
            "type": "cleanup_plan_metadata",
            "timestamp": datetime.utcnow().isoformat(),
            "mode": mode,
            "b_safe_delete_candidates": len(plan.b_safe_delete_candidates),
            "b_without_card_candidates": len(plan.b_without_card_candidates),
            "protected_a_with_card": plan.protected_a_with_card,
            "protected_b_with_card": plan.protected_b_with_card,
            "protected_recent_items": plan.protected_recent_items,
            "protected_invalid_metadata": plan.protected_invalid_metadata,
            "deleted_source_items": deleted_count,
            "backup_path": str(backup_path) if backup_path else None,
        }
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")

        # Write B-class 48h-protected candidates
        for c in plan.b_safe_delete_candidates:
            record = {
                "type": "b_safe_delete_candidate",
                "source_item_id": c.source_item_id,
                "source_key": c.source_key,
                "url": c.url,
                "title": c.title,
                "category": "b_safe_delete_candidate",
                "reason": c.reason,
                "insight_card_id": c.insight_card_id,
                "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
                "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Write B-class without-card candidates
        for c in plan.b_without_card_candidates:
            record = {
                "type": "b_without_card_candidate",
                "source_item_id": c.source_item_id,
                "source_key": c.source_key,
                "url": c.url,
                "title": c.title,
                "category": "b_without_card_candidate",
                "reason": c.reason,
                "insight_card_id": c.insight_card_id,
                "first_seen_at": c.first_seen_at.isoformat() if c.first_seen_at else None,
                "last_seen_at": c.last_seen_at.isoformat() if c.last_seen_at else None,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return export_path


# ── Apply helpers ─────────────────────────────────────────────────────────────


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


def delete_snapshot_gap_candidates(db, candidates: list[SnapshotGapCandidate]) -> int:
    """Delete SourceItems that are B-class snapshot gap safe-delete candidates.

    Returns the number of SourceItems deleted.
    """
    from app.models import SourceItem

    deleted = 0
    for c in candidates:
        item = db.query(SourceItem).filter(SourceItem.id == c.source_item_id).first()
        if item is None:
            continue
        db.delete(item)
        deleted += 1

    db.commit()
    return deleted


def delete_b_without_card_candidates(db, candidates: list[BWithoutCardCandidate]) -> int:
    """Delete B-class SourceItems that have no InsightCard.

    Returns the number of SourceItems deleted.
    """
    from app.models import SourceItem

    deleted = 0
    for c in candidates:
        item = db.query(SourceItem).filter(SourceItem.id == c.source_item_id).first()
        if item is None:
            continue
        db.delete(item)
        deleted += 1

    db.commit()
    return deleted


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
    parser.add_argument(
        "--delete-safe-snapshot-gaps",
        action="store_true",
        help="Also delete B-class snapshot gap safe-delete candidates. "
             "Requires --apply. Will not delete without this flag.",
    )
    parser.add_argument(
        "--delete-b-without-card-now",
        action="store_true",
        help="Delete ALL B-class without InsightCard to establish clean detection environment. "
             "Requires --apply. No 48h protection.",
    )
    args = parser.parse_args()

    if args.delete_safe_snapshot_gaps and not args.apply:
        print("[ERROR] --delete-safe-snapshot-gaps requires --apply")
        return 1
    if args.delete_b_without_card_now and not args.apply:
        print("[ERROR] --delete-b-without-card-now requires --apply")
        return 1

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
            database = engine.url.database
            if database and database != ":memory:":
                db_file_path = (PROJECT_ROOT / database).resolve()

        # ── Analyze ────────────────────────────────────────────────
        plan = analyze_database(db)

        # ── Export audit (both dry-run and apply) ─────────────────
        audit_path = export_audit(plan, mode)
        print(f"[AUDIT] Export written to: {audit_path}")

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
                suffix = ("b_without_card_cleanup"
                          if args.delete_b_without_card_now
                          else "snapshot_gap_cleanup")
                backup_path = backup_sqlite_db(db_file_path, suffix=suffix)
                print(f"[BACKUP] Created: {backup_path}")
            except FileNotFoundError:
                print("[ERROR] SQLite DB file not found. Cannot apply cleanup without a backup.")
                return 1
            except RuntimeError as e:
                print(f"[ERROR] {e}")
                return 1
        else:
            backup_path: Path | None = None

        print()
        print("[APPLY] Executing safe cleanup...")

        # Step 1: stale FetchRuns
        updated = apply_safe_cleanup(db)
        print(f"[APPLY] Updated {updated} stale running FetchRun(s) to failed.")

        # Step 2: B-class snapshot gap candidates (48h protected)
        deleted_snapshot_gap = 0
        if args.delete_safe_snapshot_gaps and plan.b_safe_delete_candidates:
            print()
            print(f"[APPLY] Deleting {len(plan.b_safe_delete_candidates)} B-class snapshot gap candidates...")
            deleted_snapshot_gap = delete_snapshot_gap_candidates(
                db, plan.b_safe_delete_candidates
            )
            print(f"[APPLY] Deleted {deleted_snapshot_gap} SourceItem(s).")

        # Step 3: B-class without InsightCard (no 48h protection)
        deleted_b_without_card = 0
        if args.delete_b_without_card_now and plan.b_without_card_candidates:
            print()
            print(f"[APPLY] Deleting {len(plan.b_without_card_candidates)} B-class without-card items...")
            deleted_b_without_card = delete_b_without_card_candidates(
                db, plan.b_without_card_candidates
            )
            print(f"[APPLY] Deleted {deleted_b_without_card} B-class SourceItem(s).")

        print("[APPLY] Done. Manual review items were NOT deleted (as designed).")
        print()
        total_deleted = deleted_snapshot_gap + deleted_b_without_card
        print(f"deleted_source_items: {total_deleted}")
        print(f"  b_snapshot_gap_deleted: {deleted_snapshot_gap}")
        print(f"  b_without_card_deleted: {deleted_b_without_card}")
        print(f"backup_path: {backup_path}")
        print(f"audit_export_path: {audit_path}")
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
