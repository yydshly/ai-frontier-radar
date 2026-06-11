#!/usr/bin/env python3
"""Snapshot gap repair probe — V1.0-beta.15 Phase 4.1.

Repairs missing snapshot files for A-class and B-class SourceItems by re-fetching
their URLs and saving the content as snapshot files.

Safety model:
- Default mode is DRY-RUN: prints a repair plan, writes nothing.
- --apply --limit N is required to actually fetch and save snapshots.
- Does NOT call LLM.
- Does NOT generate InsightCard.
- Does NOT delete any data.

Priority order for repair:
  1. A-class with InsightCard (high value: already has card, snapshot is critical)
  2. A-class without InsightCard
  3. B-class with InsightCard (high value: has summary, snapshot enables content access)
  4. B-class without InsightCard (lowest priority: summary exists but no card)

Usage:
    python scripts/repair_snapshot_gaps.py                        # dry-run
    python scripts/repair_snapshot_gaps.py --apply --limit 5       # apply, max 5 repairs
    python scripts/repair_snapshot_gaps.py --apply --limit 3 --prefer A  # prefer A-class
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Repair candidate dataclass ─────────────────────────────────────────────────


@dataclass
class RepairCandidate:
    """A single SourceItem that is a snapshot gap repair candidate."""
    source_item_id: int
    source_key: str
    url: str
    title: str | None
    gap_type: str          # "A" or "B"
    insight_card_id: int | None
    reason: str
    status: str            # SourceItem status field


@dataclass
class RepairResult:
    """Result of attempting to repair a single candidate."""
    source_item_id: int
    source_key: str
    url: str
    title: str | None
    gap_type: str
    insight_card_id: int | None
    action: str            # repair_candidate | repaired | failed | skipped
    result: str            # dry_run | repaired | failed | skipped
    snapshot_path: str | None
    error: str | None
    reason: str


@dataclass
class RepairPlan:
    """Holds the repair plan and results."""
    # Counts
    a_total: int = 0
    a_with_card: int = 0
    a_without_card: int = 0
    b_total: int = 0
    b_with_card: int = 0
    b_without_card: int = 0

    # Candidates (ordered by priority)
    candidates: list[RepairCandidate] = field(default_factory=list)

    # Results (filled after apply)
    results: list[RepairResult] = field(default_factory=list)


# ── Analysis ─────────────────────────────────────────────────────────────────


def analyze_snapshot_gaps(db) -> RepairPlan:
    """Analyze DB for A/B snapshot gap repair candidates. Read-only."""
    plan = RepairPlan()

    from app.models import SourceItem
    from app.application.content.content_snapshot import get_snapshot_path
    import json as json_module

    # A-class: status=fetched/compiled but no snapshot
    fetched_items = db.query(SourceItem).filter(
        SourceItem.status.in_(["fetched", "compiled"])
    ).all()
    no_snapshot_A = [i for i in fetched_items if not get_snapshot_path(i.id).exists()]
    plan.a_total = len(no_snapshot_A)
    plan.a_with_card = sum(1 for i in no_snapshot_A if i.insight_card_id)
    plan.a_without_card = plan.a_total - plan.a_with_card

    # B-class: has zh_summary in raw_metadata_json but no snapshot
    items_with_summary: list[SourceItem] = []
    for item in db.query(SourceItem).filter(SourceItem.raw_metadata_json.isnot(None)).all():
        try:
            meta = json_module.loads(item.raw_metadata_json)
            if meta.get("zh_summary") or meta.get("summary_zh"):
                items_with_summary.append(item)
        except Exception:
            pass
    no_snapshot_B = [
        i for i in items_with_summary if not get_snapshot_path(i.id).exists()
    ]
    # Exclude A-class items (status=fetched/compiled) from B-class
    a_ids = {i.id for i in no_snapshot_A}
    no_snapshot_B = [i for i in no_snapshot_B if i.id not in a_ids]

    plan.b_total = len(no_snapshot_B)
    plan.b_with_card = sum(1 for i in no_snapshot_B if i.insight_card_id)
    plan.b_without_card = plan.b_total - plan.b_with_card

    # Build candidates in priority order:
    # 1. A with card
    # 2. A without card
    # 3. B with card
    # 4. B without card
    candidates: list[RepairCandidate] = []

    a_with_card = [i for i in no_snapshot_A if i.insight_card_id]
    a_without_card = [i for i in no_snapshot_A if not i.insight_card_id]
    b_with_card = [i for i in no_snapshot_B if i.insight_card_id]
    b_without_card = [i for i in no_snapshot_B if not i.insight_card_id]

    for i in a_with_card:
        candidates.append(RepairCandidate(
            source_item_id=i.id,
            source_key=i.source_key,
            url=i.url or "",
            title=i.title,
            gap_type="A",
            insight_card_id=i.insight_card_id,
            reason="A_snapshot_missing_with_card",
            status=i.status,
        ))

    for i in a_without_card:
        candidates.append(RepairCandidate(
            source_item_id=i.id,
            source_key=i.source_key,
            url=i.url or "",
            title=i.title,
            gap_type="A",
            insight_card_id=i.insight_card_id,
            reason="A_snapshot_missing_no_card",
            status=i.status,
        ))

    for i in b_with_card:
        candidates.append(RepairCandidate(
            source_item_id=i.id,
            source_key=i.source_key,
            url=i.url or "",
            title=i.title,
            gap_type="B",
            insight_card_id=i.insight_card_id,
            reason="B_snapshot_missing_with_card",
            status=i.status,
        ))

    for i in b_without_card:
        candidates.append(RepairCandidate(
            source_item_id=i.id,
            source_key=i.source_key,
            url=i.url or "",
            title=i.title,
            gap_type="B",
            insight_card_id=i.insight_card_id,
            reason="B_snapshot_missing_no_card",
            status=i.status,
        ))

    plan.candidates = candidates
    return plan


def format_plan(plan: RepairPlan, mode: str) -> str:
    """Format RepairPlan into human-readable report."""
    lines = []
    lines.append("=" * 70)
    lines.append("AI Frontier Radar — snapshot gap repair plan")
    lines.append(f"Mode: {'APPLY' if mode == 'apply' else 'DRY-RUN'}")
    lines.append("=" * 70)
    lines.append("")

    lines.append("## snapshot_gap_repair_plan")
    lines.append(f"  A_total: {plan.a_total}")
    lines.append(f"  A_with_card: {plan.a_with_card}")
    lines.append(f"  A_without_card: {plan.a_without_card}")
    lines.append(f"  B_total: {plan.b_total}")
    lines.append(f"  B_with_card: {plan.b_with_card}")
    lines.append(f"  B_without_card: {plan.b_without_card}")
    lines.append(f"  repair_candidates: {len(plan.candidates)}")
    lines.append("")

    # Priority breakdown
    a_with = [c for c in plan.candidates if c.gap_type == "A" and c.insight_card_id]
    a_without = [c for c in plan.candidates if c.gap_type == "A" and not c.insight_card_id]
    b_with = [c for c in plan.candidates if c.gap_type == "B" and c.insight_card_id]
    b_without = [c for c in plan.candidates if c.gap_type == "B" and not c.insight_card_id]

    lines.append("  high_priority_A_with_card: {0}".format(len(a_with)))
    lines.append("  high_priority_B_with_card: {0}".format(len(b_with)))
    lines.append("  B_without_card: {0}".format(len(b_without)))
    lines.append("  manual_review_required: {0}".format(len(b_without)))
    lines.append("")

    # Show sample candidates (up to 5)
    if plan.candidates:
        lines.append("  Candidate samples (up to 5):")
        for c in plan.candidates[:5]:
            lines.append(f"    id={c.source_item_id} source_key={c.source_key} "
                         f"gap_type={c.gap_type} insight_card_id={c.insight_card_id}")
            lines.append(f"      title={str(c.title or '')[:50]}")
            lines.append(f"      url={c.url[:60]}")
            lines.append(f"      reason={c.reason}")
    lines.append("")

    # Priority explanation
    lines.append("## priority_order")
    lines.append("  1. A with card (already has InsightCard, snapshot is critical for reading)")
    lines.append("  2. A without card")
    lines.append("  3. B with card (has summary, snapshot enables content access)")
    lines.append("  4. B without card (lowest priority: summary exists but no card)")
    lines.append("")

    # Results after apply
    if plan.results:
        lines.append("## repair_results")
        repaired = [r for r in plan.results if r.result == "repaired"]
        failed = [r for r in plan.results if r.result == "failed"]
        skipped = [r for r in plan.results if r.result == "skipped"]
        lines.append(f"  total: {len(plan.results)}")
        lines.append(f"  repaired: {len(repaired)}")
        lines.append(f"  failed: {len(failed)}")
        lines.append(f"  skipped: {len(skipped)}")
        lines.append("")

        if repaired:
            lines.append("  Repaired samples:")
            for r in repaired[:3]:
                lines.append(f"    id={r.source_item_id} url={r.url[:50]} "
                             f"snapshot={r.snapshot_path}")
        if failed:
            lines.append("  Failed samples:")
            for r in failed[:3]:
                lines.append(f"    id={r.source_item_id} url={r.url[:50]} "
                             f"error={r.error}")

    if mode == "dry-run":
        lines.append("")
        lines.append("No changes written. Pass --apply --limit N to repair snapshots.")
    lines.append("=" * 70)
    return "\n".join(lines)


# ── Audit export ───────────────────────────────────────────────────────────────


def export_audit(
    plan: RepairPlan,
    mode: str,
) -> Path:
    """Export repair plan/results to JSONL. Returns the export path."""
    exports_dir = PROJECT_ROOT / "data" / "cleanup_exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"snapshot_gap_repair_plan_{timestamp}.jsonl"
    export_path = exports_dir / filename

    with open(export_path, "w", encoding="utf-8") as f:
        # Metadata record
        meta = {
            "type": "repair_plan_metadata",
            "timestamp": datetime.utcnow().isoformat(),
            "mode": mode,
            "a_total": plan.a_total,
            "a_with_card": plan.a_with_card,
            "a_without_card": plan.a_without_card,
            "b_total": plan.b_total,
            "b_with_card": plan.b_with_card,
            "b_without_card": plan.b_without_card,
            "candidates": len(plan.candidates),
        }
        f.write(json.dumps(meta, ensure_ascii=False) + "\n")

        # Candidate records (dry-run)
        for c in plan.candidates:
            record = {
                "type": "repair_candidate",
                "source_item_id": c.source_item_id,
                "source_key": c.source_key,
                "url": c.url,
                "title": c.title,
                "gap_type": c.gap_type,
                "has_insight_card": c.insight_card_id is not None,
                "insight_card_id": c.insight_card_id,
                "action": "repair_candidate",
                "result": "dry_run",
                "reason": c.reason,
                "snapshot_path": None,
                "error": None,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        # Result records (after apply)
        for r in plan.results:
            record = {
                "type": "repair_result",
                "source_item_id": r.source_item_id,
                "source_key": r.source_key,
                "url": r.url,
                "title": r.title,
                "gap_type": r.gap_type,
                "has_insight_card": r.insight_card_id is not None,
                "insight_card_id": r.insight_card_id,
                "action": r.action,
                "result": r.result,
                "reason": r.reason,
                "snapshot_path": r.snapshot_path,
                "error": r.error,
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return export_path


# ── Repair logic ───────────────────────────────────────────────────────────────


def repair_candidate(
    candidate: RepairCandidate,
) -> RepairResult:
    """Attempt to fetch URL and save a snapshot for one candidate.

    This function is read-only with respect to the database — it only
    fetches HTTP content and writes a snapshot file to disk.
    """
    from app.application.content.html_fetcher import HtmlFetchSettings, fetch_html
    from app.application.content.content_snapshot import save_snapshot

    # Build result base
    result = RepairResult(
        source_item_id=candidate.source_item_id,
        source_key=candidate.source_key,
        url=candidate.url,
        title=candidate.title,
        gap_type=candidate.gap_type,
        insight_card_id=candidate.insight_card_id,
        action="repair_candidate",
        result="dry_run",
        snapshot_path=None,
        error=None,
        reason=candidate.reason,
    )

    # Validate URL
    if not candidate.url or not candidate.url.strip():
        result.action = "skipped"
        result.result = "skipped"
        result.error = "empty_url"
        return result

    # Fetch HTML
    settings = HtmlFetchSettings.from_env()
    # Override timeout for repair: max 20 seconds
    settings = HtmlFetchSettings(
        timeout_seconds=20.0,
        max_bytes=settings.max_bytes,
        user_agent=settings.user_agent,
        min_text_length=settings.min_text_length,
        max_text_length=settings.max_text_length,
        allowed_content_types=settings.allowed_content_types,
    )

    fetch_result = fetch_html(candidate.url, settings=settings)

    if fetch_result.status == "failed":
        result.action = "failed"
        result.result = "failed"
        result.error = fetch_result.error
        return result

    if fetch_result.status == "skipped":
        result.action = "skipped"
        result.result = "skipped"
        result.error = fetch_result.error
        return result

    # Save snapshot
    snapshot_path = save_snapshot(candidate.source_item_id, fetch_result)

    if snapshot_path is None:
        result.action = "failed"
        result.result = "failed"
        result.error = "snapshot_write_failed"
        return result

    result.action = "repaired"
    result.result = "repaired"
    result.snapshot_path = str(snapshot_path)
    return result


# ── Main ─────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Snapshot gap repair probe (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually fetch URLs and save snapshots. Requires --limit.",
    )
    parser.add_argument(
        "--limit",
        type=int, default=0,
        help="Maximum number of candidates to repair in apply mode. Default: 0 (no apply).",
    )
    parser.add_argument(
        "--prefer",
        type=str, default=None,
        choices=["A", "B"],
        help="Prefer A-class or B-class candidates when --apply is used.",
    )
    args = parser.parse_args()

    if args.apply and args.limit <= 0:
        print("[ERROR] --apply requires --limit N where N > 0")
        return 1

    mode = "apply" if args.apply else "dry-run"

    print("Loading database...")
    try:
        from app.db import SessionLocal, init_db
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    init_db()
    db = SessionLocal()

    try:
        # Analyze
        plan = analyze_snapshot_gaps(db)

        # Filter by --prefer if specified
        if args.prefer == "A":
            plan.candidates = [c for c in plan.candidates if c.gap_type == "A"]
        elif args.prefer == "B":
            plan.candidates = [c for c in plan.candidates if c.gap_type == "B"]

        # Export audit
        audit_path = export_audit(plan, mode)
        print(f"[AUDIT] Export written to: {audit_path}")

        print(format_plan(plan, mode))

        if mode == "dry-run":
            print()
            print("No snapshots were fetched. Pass --apply --limit N to repair.")
            return 0

        # ── Apply ────────────────────────────────────────────────
        print()
        print(f"[APPLY] Repairing up to {args.limit} candidates...")

        candidates_to_repair = plan.candidates[:args.limit]
        results: list[RepairResult] = []

        for i, candidate in enumerate(candidates_to_repair, 1):
            print(f"[{i}/{len(candidates_to_repair)}] Repairing id={candidate.source_item_id} "
                  f"gap_type={candidate.gap_type} url={candidate.url[:50]}...")
            result = repair_candidate(candidate)
            results.append(result)

            if result.result == "repaired":
                print(f"  → REPAIRED: {result.snapshot_path}")
            elif result.result == "failed":
                print(f"  → FAILED: {result.error}")
            elif result.result == "skipped":
                print(f"  → SKIPPED: {result.error}")

        plan.results = results

        # Re-export with results
        audit_path = export_audit(plan, mode)
        print(f"[AUDIT] Updated export: {audit_path}")

        repaired = sum(1 for r in results if r.result == "repaired")
        failed = sum(1 for r in results if r.result == "failed")
        skipped = sum(1 for r in results if r.result == "skipped")

        print()
        print(f"[APPLY] Done. repaired={repaired} failed={failed} skipped={skipped}")
        return 0

    except Exception as e:
        print(f"[ERROR] Repair failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
