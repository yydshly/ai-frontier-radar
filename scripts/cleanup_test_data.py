"""Remove test/dev-pollution sources (and their items / fetch runs / cards) from
the database, leaving only real configured sources.

Months of automated tests seeded throwaway Sources (test_*, orphan_*, *_demo,
*_enq_*, …) into the working DB — 957 of 972 rows here — which pollute the
/sources page, fetch-run stats and any 'covered sources' counts. This removes
ONLY rows whose source_key matches the test patterns; the 15 real sources
(openai_news, arxiv_cs_ai, anthropic_news, …) are never touched.

Read-only by default (reports what WOULD be deleted). --apply performs the
deletion AFTER backing up the database file.

Usage:
    python scripts/cleanup_test_data.py            # dry-run report
    python scripts/cleanup_test_data.py --apply     # backup + delete
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

from app.config import DATABASE_URL  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Source, SourceItem, FetchRun, InsightCard  # noqa: E402

_TEST_MARKERS = ("test", "orphan", "demo", "abc123", "_enq_", "_filter_",
                 "_err_", "dummy", "example_", "mock")


def is_test_source(key: str) -> bool:
    k = (key or "").lower()
    return any(m in k for m in _TEST_MARKERS)


def _backup_db() -> str | None:
    if not DATABASE_URL.startswith("sqlite"):
        return None
    db_path = Path(DATABASE_URL.split("///", 1)[1])
    if not db_path.exists():
        return None
    # Flush WAL into the main file so the copy is complete.
    with engine.begin() as conn:
        conn.exec_driver_sql("PRAGMA wal_checkpoint(TRUNCATE)")
    backups = db_path.parent / "backups"
    backups.mkdir(parents=True, exist_ok=True)
    dst = backups / f"{db_path.name}.cleanup_backup_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(db_path, dst)
    return str(dst)


def main() -> int:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        sources = db.query(Source).all()
        test_sources = [s for s in sources if is_test_source(s.source_key)]
        test_ids = {s.id for s in test_sources}
        test_keys = {s.source_key for s in test_sources}
        keep = [s.source_key for s in sources if s.id not in test_ids]

        items = db.query(SourceItem).filter(
            (SourceItem.source_id.in_(test_ids)) | (SourceItem.source_key.in_(test_keys))
        ).all()
        item_ids = [it.id for it in items]
        card_ids = [it.insight_card_id for it in items if it.insight_card_id]
        run_count = db.query(FetchRun).filter(FetchRun.source_key.in_(test_keys)).count() if test_keys else 0

        print("=" * 64)
        print(f"Cleanup test/dev pollution ({'APPLY' if apply else 'DRY-RUN'})")
        print("=" * 64)
        print(f"  sources:    total={len(sources)}  test={len(test_sources)}  keep={len(keep)}")
        print(f"  source_items to delete: {len(item_ids)}")
        print(f"  fetch_runs to delete:   {run_count}")
        print(f"  insight_cards to delete: {len(card_ids)}")
        print(f"  KEEP (real): {sorted(keep)}")

        if not apply:
            print("\nDry-run only. Re-run with --apply to back up + delete.")
            return 0
        if not test_ids:
            print("\nNothing to delete.")
            return 0

        backup = _backup_db()
        print(f"\n  backup: {backup or '(skipped — non-sqlite)'}")

        # Delete children first, then parents (FK enforcement is off, but keep
        # a sane order to avoid orphans).
        if card_ids:
            db.query(InsightCard).filter(InsightCard.id.in_(card_ids)).delete(synchronize_session=False)
        if item_ids:
            db.query(SourceItem).filter(SourceItem.id.in_(item_ids)).delete(synchronize_session=False)
        if test_keys:
            db.query(FetchRun).filter(FetchRun.source_key.in_(test_keys)).delete(synchronize_session=False)
        db.query(Source).filter(Source.id.in_(test_ids)).delete(synchronize_session=False)
        db.commit()

        remaining = db.query(Source).count()
        print(f"  deleted. sources remaining: {remaining}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
