#!/usr/bin/env python3
"""Compile 1 SourceItem to InsightCard — V1.0-beta.16 Phase 4.2.

Usage:
    python scripts/compile_one_insight_card.py
    python scripts/compile_one_insight_card.py --item-id 2292
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
        description="Compile 1 SourceItem to InsightCard."
    )
    parser.add_argument(
        "--item-id",
        type=int, default=None,
        help="SourceItem ID to compile. Default: auto-select a valid discovered item.",
    )
    args = parser.parse_args()

    print("[COMPILE] Loading database...")
    try:
        from app.db import SessionLocal, init_db
        from app.models import SourceItem
        from app.application.source_items.compile_service import SourceItemCompileService
    except Exception as e:
        print(f"[ERROR] Failed to import app modules: {e}")
        return 1

    init_db()
    db = SessionLocal()

    try:
        # Find or use specified item
        if args.item_id:
            item = db.query(SourceItem).filter(SourceItem.id == args.item_id).first()
            if not item:
                print(f"[ERROR] SourceItem id={args.item_id} not found.")
                return 1
        else:
            # Auto-select: prefer an arxiv item with URL (likely to have abstract)
            item = (
                db.query(SourceItem)
                .filter(
                    SourceItem.status == "discovered",
                    SourceItem.url.like("https://arxiv.org%"),
                    SourceItem.url.isnot(None),
                )
                .first()
            )
            if not item:
                # Fallback: any discovered item with URL
                item = (
                    db.query(SourceItem)
                    .filter(
                        SourceItem.status == "discovered",
                        SourceItem.url.isnot(None),
                    )
                    .first()
                )

        if not item:
            print("[ERROR] No eligible SourceItem found.")
            return 1

        print(f"[COMPILE] Compiling SourceItem id={item.id}")
        print(f"  source_key: {item.source_key}")
        print(f"  title:     {item.title}")
        print(f"  url:       {item.url}")
        print(f"  status:    {item.status}")
        print()

        svc = SourceItemCompileService(db)
        result = svc.compile_item(item.id)

        print(f"[COMPILE] Result:")
        print(f"  ok:           {result.ok}")
        print(f"  status:       {result.status}")
        print(f"  insight_card_id: {result.insight_card_id}")
        print(f"  message:      {result.message}")

        # Refresh item to see updated state
        db.refresh(item)
        print()
        print(f"[COMPILE] After compile:")
        print(f"  SourceItem.status:      {item.status}")
        print(f"  SourceItem.insight_card_id: {item.insight_card_id}")

        if result.insight_card_id:
            from app.models import InsightCard
            card = db.query(InsightCard).filter(InsightCard.id == result.insight_card_id).first()
            if card:
                print(f"  InsightCard.status:  {card.status}")
                print(f"  InsightCard.summary_zh (first 80 chars): {str(card.summary_zh or '')[:80]}")

        return 0 if result.ok else 1

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
