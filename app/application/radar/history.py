"""Per-day history (P5): index of past days + a read-only per-day view.

A "day" is the anchor period (08:00→08:00). Reports and audio are already
persisted by date_label; articles are queried by first_seen_at within the day's
anchor window. This module only reads — no writes, no LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models import Source, SourceItem
from app.application.radar.daily_scope import anchor_window_for_date
from app.application.radar.daily_report_store import (
    list_daily_report_dates,
    list_final_daily_report_dates,
    load_daily_report,
    load_final_daily_report,
)


@dataclass(frozen=True)
class HistoryDay:
    date_label: str
    report_title: str | None
    item_count: int
    audio_count: int
    has_report: bool


@dataclass(frozen=True)
class HistoryGroup:
    source_name: str
    items: list  # list[dict]


@dataclass(frozen=True)
class HistoryDayView:
    date_label: str
    report: dict | None
    audio_jobs: list
    item_count: int
    source_count: int
    groups: list  # list[HistoryGroup]


def _valid_items_in_window(db, date_label: str) -> list[SourceItem]:
    start, end = anchor_window_for_date(date_label)
    return (
        db.query(SourceItem)
        .join(Source, Source.id == SourceItem.source_id)
        .filter(
            Source.enabled.is_(True),
            SourceItem.url.isnot(None),
            SourceItem.url != "",
            SourceItem.title.isnot(None),
            SourceItem.title != "",
            SourceItem.first_seen_at >= start,
            SourceItem.first_seen_at < end,
        )
        .order_by(SourceItem.first_seen_at.desc(), SourceItem.id.desc())
        .all()
    )


def _audio_jobs_for(date_label: str) -> list:
    from app.application.radar.daily_audio_jobs import (
        list_daily_audio_jobs,
        is_daily_audio_job_playable,
    )
    return [
        j for j in list_daily_audio_jobs(limit=100)
        if j.date_label == date_label
        and j.status == "generated"
        and is_daily_audio_job_playable(j)
    ]


def list_history_days(db) -> list[HistoryDay]:
    """All past days that have a persisted report, newest first."""
    days: list[HistoryDay] = []
    date_labels = sorted(
        set(list_final_daily_report_dates()) | set(list_daily_report_dates()),
        reverse=True,
    )
    for date_label in date_labels:
        report = load_final_daily_report(date_label) or load_daily_report(date_label)
        frozen_articles = (
            report.get("articles")
            if report and report.get("report_kind") == "final"
            else None
        )
        items = _valid_items_in_window(db, date_label) if frozen_articles is None else []
        audio_jobs = _audio_jobs_for(date_label)
        if report:
            from app.application.radar.daily_audio_jobs import select_daily_audio_job
            selected_audio = select_daily_audio_job(
                audio_jobs,
                date_label=date_label,
                report_version=report.get("version_id"),
            )
            audio_count = 1 if selected_audio else 0
        else:
            audio_count = 0
        days.append(HistoryDay(
            date_label=date_label,
            report_title=(report or {}).get("title") if report else None,
            item_count=len(frozen_articles) if frozen_articles is not None else len(items),
            audio_count=audio_count,
            has_report=report is not None,
        ))
    return days


def build_history_day_view(db, date_label: str) -> HistoryDayView:
    """Read-only detail for one past day: its report, audio, and articles."""
    from app.application.candidates.display import build_candidate_display_card

    report = load_final_daily_report(date_label) or load_daily_report(date_label)
    all_audio_jobs = _audio_jobs_for(date_label)
    from app.application.radar.daily_audio_jobs import select_daily_audio_job
    selected_audio = select_daily_audio_job(
        all_audio_jobs,
        date_label=date_label,
        report_version=(report or {}).get("version_id"),
    )
    audio_jobs = [selected_audio] if selected_audio else []
    frozen_articles = (
        report.get("articles")
        if report and report.get("report_kind") == "final"
        else None
    )
    items = _valid_items_in_window(db, date_label) if frozen_articles is None else []

    keys = {it.source_key for it in items}
    names = {
        s.source_key: s.name
        for s in db.query(Source).filter(Source.source_key.in_(keys)).all()
    } if keys else {}

    grouped: dict[str, list] = {}
    if frozen_articles is not None:
        for article in frozen_articles:
            if not isinstance(article, dict):
                continue
            source_key = str(article.get("source_key") or "")
            grouped.setdefault(source_key, []).append({
                "item_id": article.get("item_id"),
                "title": article.get("title") or "无标题",
                "zh_preview": article.get("zh_one_liner"),
                "url": article.get("url"),
                "time_label": "正式日报快照",
                "insight_card_id": article.get("insight_card_id"),
            })
            names[source_key] = str(article.get("source_name") or source_key)
    else:
        for it in items:
            card = build_candidate_display_card(it)
            grouped.setdefault(it.source_key, []).append({
                "item_id": it.id,
                "title": card.title,
                "zh_preview": card.primary_text if card.uses_zh_one_liner else None,
                "url": card.url,
                "time_label": card.time_label,
                "insight_card_id": it.insight_card_id,
            })
    groups = [
        HistoryGroup(source_name=names.get(k, k), items=v)
        for k, v in grouped.items()
    ]

    return HistoryDayView(
        date_label=date_label,
        report=report,
        audio_jobs=audio_jobs,
        item_count=len(frozen_articles) if frozen_articles is not None else len(items),
        source_count=len(groups),
        groups=groups,
    )
