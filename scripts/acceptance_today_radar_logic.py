#!/usr/bin/env python3
"""Isolated acceptance test for RadarTodayService query logic.

Uses a temporary SQLite database — does NOT touch data/ai_frontier_radar.db,
does NOT access the network, does NOT call any LLM.

Verifies that RadarTodayService correctly filters (or includes) the following
scenarios:
  1. valid SourceItem appears in today radar
  2. item from disabled source does NOT appear (if source.enabled filter exists)
  3. item without url does NOT appear (if such a filter exists)
  4. item without title does NOT appear (if such a filter exists)
  5. item whose source_id references non-existent Source does NOT appear
  6. item outside the today window does NOT appear

If a guard is missing (item leaks through), it is documented as a risk_point.
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── Test result tracking ──────────────────────────────────────────────────────

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"  # guard not implemented — documented as risk


class TestResult:
    def __init__(self, name: str, status: str, detail: str = ""):
        self.name = name
        self.status = status  # PASS / FAIL / SKIP
        self.detail = detail  # explanation

    def __repr__(self):
        icon = {"PASS": "✓", "FAIL": "✗", "SKIP": "⊘"}[self.status]
        msg = f"  [{self.status}] {self.name}"
        if self.detail:
            msg += f"\n        {self.detail}"
        return msg


# ── Isolated test DB setup ───────────────────────────────────────────────────

def create_isolated_db():
    """Create an isolated temp SQLite DB with schema, return (engine, Session)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db import Base
    from app.models import Source, SourceItem, FetchRun, InsightCard

    # Use a real temp file (not :memory:) so SQLAlchemy can open it properly
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".db")
    import os
    os.close(tmp_fd)

    engine = create_engine(f"sqlite:///{tmp_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return engine, Session, tmp_path


def add_minimal_sources(session):
    """Add minimal source rows needed for foreign-key integrity."""
    from app.models import Source
    sources = [
        Source(
            id=1,
            source_key="test_enabled",
            name="Test Enabled Source",
            description="A test source that is enabled",
            source_type="rss",
            category="blog",
            enabled=True,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        ),
        Source(
            id=2,
            source_key="test_disabled",
            name="Test Disabled Source",
            description="A test source that is disabled",
            source_type="rss",
            category="blog",
            enabled=False,
            fetch_strategy="rss",
            relevance_hint="",
            fetch_interval_hours=24,
        ),
    ]
    for s in sources:
        session.add(s)
    session.commit()


def add_source_item(
    session,
    *,
    id: int,
    source_id: int,
    source_key: str,
    url: str,
    title: str,
    status: str = "discovered",
    hours_ago: int = 0,  # 0 = now, positive = past
    published_at: str | None = None,
    insight_card_id: int | None = None,
) -> "SourceItem":
    """Add a SourceItem with timestamps relative to now."""
    from app.models import SourceItem
    item = SourceItem(
        id=id,
        source_id=source_id,
        source_key=source_key,
        url=url,
        title=title,
        status=status,
        insight_card_id=insight_card_id,
    )
    if hours_ago == 0:
        now = datetime.utcnow()
    else:
        now = datetime.utcnow() - timedelta(hours=hours_ago)

    item.first_seen_at = now
    item.last_seen_at = now
    if published_at:
        item.published_at = published_at
    session.add(item)
    session.commit()
    return item


def add_insight_card(session, id: int, source_title: str = "Test Card") -> "InsightCard":
    """Add an InsightCard."""
    from app.models import InsightCard, CardStatus
    card = InsightCard(
        id=id,
        source_url="https://example.com/test",
        source_title=source_title,
        status=CardStatus.COMPLETED,
        summary_zh="Test summary",
    )
    session.add(card)
    session.commit()
    return card


# ── RadarTodayService wrapper (isolated) ─────────────────────────────────────

def build_today_view_isolated(session, hours: int = 24, limit: int = 50):
    """Build a RadarTodayView using an isolated session (no globals)."""
    from app.application.radar.today import RadarTodayService

    service = RadarTodayService(session)
    return service.build_today_view(hours=hours, limit=limit)


def get_today_item_ids(session, hours: int = 24, limit: int = 50) -> set[int]:
    """Return the set of SourceItem ids in today's radar view."""
    view = build_today_view_isolated(session, hours=hours, limit=limit)
    ids: set[int] = set()
    for section in view.sections:
        for item in section.items:
            ids.add(item.id)
    return ids


def get_quality_filter_stats(session, hours: int = 24, limit: int = 50):
    """Return the QualityFilterStats from today's radar view."""
    view = build_today_view_isolated(session, hours=hours, limit=limit)
    return view.quality_filter_stats


# ── Tests ─────────────────────────────────────────────────────────────────────

def run_tests() -> list[TestResult]:
    results: list[TestResult] = []
    engine, Session, tmp_path = create_isolated_db()

    try:
        session = Session()
        add_minimal_sources(session)

        now = datetime.utcnow()
        cutoff = now - timedelta(hours=24)

        # ── Test 1: valid item appears ─────────────────────────────────────
        item1 = add_source_item(
            session, id=1, source_id=1, source_key="test_enabled",
            url="https://example.com/valid", title="Valid Article",
            hours_ago=1,
        )
        ids = get_today_item_ids(session)
        if item1.id in ids:
            results.append(TestResult(
                "valid SourceItem appears in today radar",
                PASS,
                f"item id={item1.id} found in {len(ids)} total items"
            ))
        else:
            results.append(TestResult(
                "valid SourceItem appears in today radar",
                FAIL,
                f"item id={item1.id} NOT found — radar returned: {ids}"
            ))

        # ── Test 2: item without URL ─────────────────────────────────────────
        item2 = add_source_item(
            session, id=2, source_id=1, source_key="test_enabled",
            url="", title="Item Without URL",
            hours_ago=1,
        )
        ids = get_today_item_ids(session)
        if item2.id in ids:
            results.append(TestResult(
                "item without url does NOT appear",
                FAIL,
                f"item id={item2.id} was included — url='' should be filtered by guard."
            ))
        else:
            results.append(TestResult(
                "item without url does NOT appear",
                PASS,
                f"item id={item2.id} was correctly excluded by url guard"
            ))

        # ── Test 3: item without title ─────────────────────────────────────
        item3 = add_source_item(
            session, id=3, source_id=1, source_key="test_enabled",
            url="https://example.com/no-title", title="",
            hours_ago=1,
        )
        ids = get_today_item_ids(session)
        if item3.id in ids:
            results.append(TestResult(
                "item without title does NOT appear",
                FAIL,
                f"item id={item3.id} was included — title='' should be filtered by guard."
            ))
        else:
            results.append(TestResult(
                "item without title does NOT appear",
                PASS,
                f"item id={item3.id} was correctly excluded by title guard"
            ))

        # ── Test 4: item from disabled source ───────────────────────────────
        item4 = add_source_item(
            session, id=4, source_id=2, source_key="test_disabled",
            url="https://example.com/disabled-source", title="Disabled Source Article",
            hours_ago=1,
        )
        ids = get_today_item_ids(session)
        if item4.id in ids:
            results.append(TestResult(
                "item from disabled source does NOT appear",
                FAIL,
                f"item id={item4.id} was included — disabled source should be filtered by guard."
            ))
        else:
            results.append(TestResult(
                "item from disabled source does NOT appear",
                PASS,
                f"item id={item4.id} was correctly excluded by enabled-source guard"
            ))

        # ── Test 5: item with non-existent source_id ───────────────────────
        item5 = add_source_item(
            session, id=5, source_id=999, source_key="nonexistent_source",
            url="https://example.com/orphan", title="Orphan Article",
            hours_ago=1,
        )
        ids = get_today_item_ids(session)
        if item5.id in ids:
            results.append(TestResult(
                "item with non-existent source_id does NOT appear",
                FAIL,
                f"item id={item5.id} was included — orphan source_id should be filtered by join."
            ))
        else:
            results.append(TestResult(
                "item with non-existent source_id does NOT appear",
                PASS,
                f"item id={item5.id} was correctly excluded by Source join guard"
            ))

        # ── Test 6: item outside today window ───────────────────────────────
        item6 = add_source_item(
            session, id=6, source_id=1, source_key="test_enabled",
            url="https://example.com/old", title="Old Article",
            hours_ago=48,  # 48 hours ago — outside 24-hour window
        )
        ids = get_today_item_ids(session)
        if item6.id not in ids:
            results.append(TestResult(
                "item outside today window does NOT appear",
                PASS,
                f"item id={item6.id} (48h old) correctly excluded"
            ))
        else:
            results.append(TestResult(
                "item outside today window does NOT appear",
                FAIL,
                f"item id={item6.id} (48h old) was included — should be outside 24h window"
            ))

        # ── Test 6b: re-seeing an old item does not make it newly discovered ──
        item6b = add_source_item(
            session, id=9, source_id=1, source_key="test_enabled",
            url="https://example.com/old-reseen", title="Old Article Seen Again",
            hours_ago=48,
        )
        item6b.last_seen_at = now
        session.commit()
        ids = get_today_item_ids(session)
        if item6b.id not in ids:
            results.append(TestResult(
                "old item re-seen today does NOT appear as new",
                PASS,
                "first_seen_at remains outside the daily window"
            ))
        else:
            results.append(TestResult(
                "old item re-seen today does NOT appear as new",
                FAIL,
                "last_seen_at must not make an old article newly discovered"
            ))

        # ── Test 7: item with insight_card already generated ───────────────
        card = add_insight_card(session, id=1, source_title="Has InsightCard")
        item7 = add_source_item(
            session, id=7, source_id=1, source_key="test_enabled",
            url="https://example.com/with-card", title="Has InsightCard Article",
            status="compiled", insight_card_id=card.id,
            hours_ago=1,
        )
        ids = get_today_item_ids(session)
        if item7.id in ids:
            results.append(TestResult(
                "item with existing InsightCard appears (expected)",
                PASS,
                "Items with insight_card_id are NOT filtered out — this is expected behavior"
            ))
        else:
            results.append(TestResult(
                "item with existing InsightCard appears",
                FAIL,
                f"item id={item7.id} should appear (insight cards are not filtered)"
            ))

        # ── Test 8: snapshot-missing item (A/B) appears ───────────────────
        # This is a risk_point — such items may appear with broken card state
        item8 = add_source_item(
            session, id=8, source_id=1, source_key="test_enabled",
            url="https://example.com/snapshot-missing", title="Snapshot Missing Article",
            status="fetched",  # has content but snapshot file won't exist in isolated DB
            hours_ago=1,
        )
        ids = get_today_item_ids(session)
        if item8.id in ids:
            results.append(TestResult(
                "snapshot-missing item (status=fetched) appears (expected — data quality issue)",
                PASS,
                "Items with status=fetched/compiled appear even without snapshot file. "
                "This is expected by the current code. The missing snapshot is a data "
                "quality issue that manifests as empty content in the reading panel."
            ))
        else:
            results.append(TestResult(
                "snapshot-missing item appears",
                FAIL,
                f"item id={item8.id} unexpectedly excluded"
            ))

        # ── Test 9: quality_filter_stats total ───────────────────────────────
        stats = get_quality_filter_stats(session)
        # 4 invalid items were added: item2(url=''), item3(title=''),
        # item4(disabled source), item5(orphan source_id)
        expected_total = 4
        if stats and stats.total_filtered == expected_total:
            results.append(TestResult(
                "quality_filter_stats.total_filtered == 4",
                PASS,
                f"total_filtered={stats.total_filtered}"
            ))
        else:
            results.append(TestResult(
                "quality_filter_stats.total_filtered == 4",
                FAIL,
                f"expected {expected_total}, got {stats.total_filtered if stats else 'None'}"
            ))

        # ── Test 10: quality_filter_stats breakdown ─────────────────────────
        if stats:
            broken = []
            if stats.orphan_source != 1:
                broken.append(f"orphan_source: expected 1, got {stats.orphan_source}")
            if stats.disabled_source != 1:
                broken.append(f"disabled_source: expected 1, got {stats.disabled_source}")
            if stats.missing_url != 1:
                broken.append(f"missing_url: expected 1, got {stats.missing_url}")
            if stats.missing_title != 1:
                broken.append(f"missing_title: expected 1, got {stats.missing_title}")
            if not broken:
                results.append(TestResult(
                    "quality_filter_stats breakdown correct",
                    PASS,
                    f"orphan={stats.orphan_source}, disabled={stats.disabled_source}, "
                    f"no_url={stats.missing_url}, no_title={stats.missing_title}"
                ))
            else:
                results.append(TestResult(
                    "quality_filter_stats breakdown correct",
                    FAIL,
                    "; ".join(broken)
                ))
        else:
            results.append(TestResult(
                "quality_filter_stats breakdown correct",
                FAIL,
                "quality_filter_stats is None"
            ))

    finally:
        session.close()
        engine.dispose()
        import os
        try:
            os.unlink(tmp_path)
        except Exception:
            pass

    return results


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 70)
    print("RadarTodayService — isolated acceptance tests")
    print("Using temporary SQLite DB — no real data touched")
    print("=" * 70)
    print()

    results = run_tests()

    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")

    print("Results:")
    print()
    for r in results:
        print(f"  [{r.status}] {r.name}")
        if r.detail:
            print(f"         {r.detail}")
        print()

    print("=" * 70)
    print(f"Summary: {passed} passed, {failed} failed, {skipped} skipped")
    print()

    if skipped > 0:
        print("[NOTE] SKIP = guard not implemented in current code.")
        print("        These are documented as recommended_minimal_guards.")
        print()

    if failed > 0:
        print("[FAIL] Some tests failed — see above.")
        return 1

    print("[OK] All implemented guards pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
