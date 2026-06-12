from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Source, SourceItem
from app.application.radar.daily_finalization import (
    finalize_daily_report,
    pending_finalization_dates,
)
from app.application.radar.daily_report import (
    DailyReportResult,
    build_daily_report_input,
)
from app.application.radar.daily_report_store import (
    load_final_daily_report,
    save_final_daily_report,
)
from app.application.radar.daily_scope import latest_completed_date_label


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _source(db) -> Source:
    source = Source(
        source_key="test_finalization",
        name="Test",
        description="Test",
        source_type="rss",
        category="research",
        tags_json="[]",
        enabled=True,
        fetch_strategy="rss",
        relevance_hint="",
        fetch_interval_hours=24,
    )
    db.add(source)
    db.commit()
    return source


def test_fixed_date_report_input_uses_closed_anchor_window():
    db = _session()
    source = _source(db)
    summary = json.dumps({
        "zh_one_liner": "一句话",
        "zh_summary": "详细摘要",
    }, ensure_ascii=False)
    db.add_all([
        SourceItem(
            source_id=source.id,
            source_key=source.source_key,
            url="https://example.com/in",
            title="inside",
            status="discovered",
            raw_metadata_json=summary,
            first_seen_at=datetime(2026, 6, 12, 12, 0),
        ),
        SourceItem(
            source_id=source.id,
            source_key=source.source_key,
            url="https://example.com/next",
            title="next period",
            status="discovered",
            raw_metadata_json=summary,
            first_seen_at=datetime(2026, 6, 13, 0, 0),
        ),
    ])
    db.commit()

    payload = build_daily_report_input(db, date_label="2026-06-12")

    assert payload.date_label == "2026-06-12"
    assert payload.item_count == 1
    assert payload.sources[0].title == "inside"


def test_final_report_is_not_overwritten(tmp_path):
    first = DailyReportResult(
        status="generated",
        date_label="2026-06-12",
        input_item_count=1,
        message="ok",
        title="first",
        overview="overview",
        highlights=["one"],
        highlight_references=[[]],
        input_fingerprint="a",
    )
    second = DailyReportResult(
        status="generated",
        date_label="2026-06-12",
        input_item_count=2,
        message="ok",
        title="second",
        overview="changed",
        highlights=["two"],
        highlight_references=[[]],
        input_fingerprint="b",
    )
    kwargs = {
        "articles": [],
        "window_start": datetime(2026, 6, 12),
        "window_end": datetime(2026, 6, 13),
        "root_dir": tmp_path,
    }

    stored_first = save_final_daily_report(first, **kwargs)
    stored_second = save_final_daily_report(second, **kwargs)
    loaded = load_final_daily_report("2026-06-12", root_dir=tmp_path)

    assert stored_first is not None
    assert stored_second is not None
    assert loaded is not None
    assert loaded["title"] == "first"
    assert stored_second["title"] == "first"


def test_latest_completed_period_is_previous_label_at_anchor():
    now = datetime(2026, 6, 13, 0, 0)

    assert latest_completed_date_label(now) == "2026-06-12"


def test_pending_dates_are_oldest_first_and_skip_existing(tmp_path):
    result = DailyReportResult(
        status="generated",
        date_label="2026-06-11",
        input_item_count=1,
        message="ok",
        title="saved",
        overview="overview",
        highlights=[],
        highlight_references=[],
    )
    save_final_daily_report(
        result,
        articles=[],
        window_start=datetime(2026, 6, 11),
        window_end=datetime(2026, 6, 12),
        root_dir=tmp_path,
    )

    pending = pending_finalization_dates(
        now=datetime(2026, 6, 13, 0, 0),
        max_days=3,
        root_dir=tmp_path,
    )

    assert pending == ["2026-06-10", "2026-06-12"]

    with_audio_retry = pending_finalization_dates(
        now=datetime(2026, 6, 13, 0, 0),
        max_days=3,
        root_dir=tmp_path,
        include_audio_incomplete=True,
    )
    assert with_audio_retry == ["2026-06-10", "2026-06-11", "2026-06-12"]


def test_finalize_saves_article_summary_snapshot(tmp_path, monkeypatch):
    class Provider:
        def generate(self, *, system_prompt, user_prompt):
            return {
                "title": "正式日报",
                "overview": "完整周期概览",
                "highlights": [{
                    "text": "关键变化",
                    "source_item_ids": [1],
                }],
            }

    monkeypatch.setenv("DAILY_REPORT_ENABLED", "true")
    db = _session()
    source = _source(db)
    db.add(SourceItem(
        id=1,
        source_id=source.id,
        source_key=source.source_key,
        url="https://example.com/article",
        canonical_url="https://example.com/canonical",
        title="Article",
        status="discovered",
        raw_metadata_json=json.dumps({
            "zh_one_liner": "一句话摘要",
            "zh_summary": "结算时保存的详细摘要",
        }, ensure_ascii=False),
        first_seen_at=datetime(2026, 6, 12, 12, 0),
    ))
    db.commit()

    result = finalize_daily_report(
        db,
        "2026-06-12",
        provider=Provider(),
        generate_audio=False,
        root_dir=tmp_path,
    )
    stored = load_final_daily_report("2026-06-12", root_dir=tmp_path)

    assert result.status == "finalized"
    assert stored is not None
    assert stored["report_kind"] == "final"
    assert stored["audio_status"] == "skipped"
    assert stored["articles"][0]["zh_summary"] == "结算时保存的详细摘要"
    assert stored["articles"][0]["url"] == "https://example.com/canonical"
