#!/usr/bin/env python3
"""Compile selected InsightCard candidates — V1.0-beta.16 Phase 4.3.

Default dry-run (read-only). Use --apply to actually compile.

Usage:
    python scripts/compile_selected_insight_cards.py                    # dry-run
    python scripts/compile_selected_insight_cards.py --limit 3           # dry-run, top 3
    python scripts/compile_selected_insight_cards.py --apply --limit 3   # apply, top 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile selected InsightCard candidates (dry-run by default)."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually compile the candidates. Without this flag the script is dry-run.",
    )
    parser.add_argument(
        "--limit",
        type=int, default=3,
        help="Maximum candidates to compile (default: 3).",
    )
    parser.add_argument(
        "--hours", type=int, default=24,
        help="Time window in hours for candidate selection (default: 24).",
    )
    parser.add_argument(
        "--per-source-limit", type=int, default=3,
        help="Max candidates per source (default: 3).",
    )
    args = parser.parse_args()

    mode = "APPLY" if args.apply else "DRY-RUN"

    print(f"[SELECT] Loading database...")
    try:
        from app.db import SessionLocal, init_db
        from app.models import SourceItem
        from app.application.source_items.compile_service import SourceItemCompileService
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    # Import selection logic
    try:
        from scripts.select_today_compile_candidates import select_candidates
    except Exception:
        # Fallback: inline selection if import fails
        def select_candidates(db, hours, limit, per_source_limit):
            from collections import defaultdict
            from datetime import timedelta
            from app.models import SourceItem
            cutoff = datetime.utcnow() - timedelta(hours=hours)
            items = (
                db.query(SourceItem)
                .filter(
                    (SourceItem.first_seen_at >= cutoff) |
                    (SourceItem.last_seen_at >= cutoff),
                )
                .all()
            )
            return []  # simplified fallback

    init_db()
    db = SessionLocal()

    try:
        print(f"[SELECT] Selecting candidates (hours={args.hours}, limit={args.limit}, "
              f"per_source_limit={args.per_source_limit})...")
        candidates = select_candidates(
            db,
            hours=args.hours,
            limit=args.limit,
            per_source_limit=args.per_source_limit,
        )

        print(f"=" * 70)
        print(f"Compile Selected InsightCards — {mode}")
        print(f"=" * 70)
        print(f"  mode: {mode}")
        print(f"  candidates_found: {len(candidates)}")
        print(f"  compile_limit: {args.limit}")
        print(f"")

        if not candidates:
            print("  No candidates found.")
            print(f"=" * 70)
            return 0

        # Show candidates
        print("  Candidates:")
        for c in candidates:
            print(f"    [{c.rank}] id={c.source_item_id} source_key={c.source_key} "
                  f"basis={c.compile_basis} score={c.score}")
            print(f"         title={c.title[:50]}")
        print("")

        if mode == "DRY-RUN":
            print("  [DRY-RUN] No changes made. Pass --apply --limit N to compile.")
            print(f"=" * 70)
            return 0

        # ── Apply ────────────────────────────────────────────────────────────
        print(f"  [APPLY] Compiling {len(candidates)} candidates...")
        print("")

        service = SourceItemCompileService(db)
        results: list[dict] = []

        for c in candidates:
            item = db.query(SourceItem).filter(SourceItem.id == c.source_item_id).first()
            if not item:
                result = {
                    "source_item_id": c.source_item_id,
                    "status": "not_found",
                    "insight_card_id": None,
                    "ok": False,
                    "message": "SourceItem not found",
                }
            else:
                print(f"  [{c.rank}/{len(candidates)}] Compiling id={c.source_item_id} "
                      f"source_key={c.source_key} ...")
                res = service.compile_item(c.source_item_id)
                result = {
                    "source_item_id": c.source_item_id,
                    "status": res.status,
                    "insight_card_id": res.insight_card_id,
                    "ok": res.ok,
                    "message": res.message,
                }
                if res.ok:
                    print(f"    [OK] card_id={res.insight_card_id} — {res.message}")
                else:
                    print(f"    [FAIL] {res.message}")

            results.append(result)

        # Summary
        ok_count = sum(1 for r in results if r["ok"])
        fail_count = len(results) - ok_count
        card_ids = [r["insight_card_id"] for r in results if r["insight_card_id"]]

        print("")
        print(f"  Summary:")
        print(f"    total:     {len(results)}")
        print(f"    success:   {ok_count}")
        print(f"    failed:    {fail_count}")
        if card_ids:
            print(f"    card_ids:  {card_ids}")
        print(f"=" * 70)
        return 0

    except Exception as e:
        db.rollback()
        print(f"[ERROR] Compile failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
