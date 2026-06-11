"""Read-only daily digest aggregation for the today-radar (P-003 step 1).

Aggregates *today's* newly discovered SourceItems into a compact "今日编译概览"
summary for the radar sidebar. This is the data foundation for the future
"今日核心报告卡片"; it does NOT call any LLM and does NOT write to the database.

Phase boundaries:
- Phase C (this module): read-only aggregation + counts + a few top items.
- Phase D (later): LLM core summary generation (cost-gated, explicit).
- Phase E (later): voice broadcast (TTS, optional / toggleable).

User-facing "today" means the rolling recent window (default 24 hours).
Items are counted by their ``first_seen_at`` inside this window.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_

from app.models import Source, SourceItem
from app.application.radar.daily_scope import recent_valid_items_query, SUMMARY_MARKERS
from app.application.radar.settings import get_daily_scope_settings

# Single source of truth for summary markers lives in daily_scope (was a local
# 3-element tuple here that missed "zh_summary" and undercounted summaries).
_SUMMARY_MARKERS = SUMMARY_MARKERS

# Cap on how many top items to surface in the digest.
_TOP_ITEMS_LIMIT = 5


@dataclass(frozen=True)
class DailyDigestItem:
    """One surfaced item in the daily digest (display-only)."""

    item_id: int
    title: str
    zh_preview: str | None
    source_key: str
    insight_card_id: int | None


@dataclass(frozen=True)
class DailyDigestView:
    """Read-only aggregation of today's newly discovered content."""

    date_label: str
    new_items_count: int
    summarized_count: int
    card_count: int
    source_count: int
    top_items: list[DailyDigestItem]


def _start_of_utc_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def build_daily_digest_view(db, *, now: datetime | None = None) -> DailyDigestView:
    """Aggregate today's newly discovered SourceItems. Read-only, no LLM.

    Counts are computed in SQL (no full-table load into Python). Only the few
    surfaced top items are turned into display previews via the canonical
    candidate display helper.
    """
    if now is None:
        now = datetime.utcnow()
    day_start = _start_of_utc_day(now)

    base = recent_valid_items_query(db, now=now)

    new_items_count = base.count()

    summarized_count = (
        base.filter(
            or_(*[SourceItem.raw_metadata_json.like(f"%{m}%") for m in _SUMMARY_MARKERS])
        ).count()
    )

    card_count = base.filter(SourceItem.insight_card_id.isnot(None)).count()

    source_count = (
        recent_valid_items_query(db, now=now)
        .with_entities(SourceItem.source_key)
        .distinct()
        .count()
    )

    # Top items: prefer those that already have a Chinese one-liner, newest first.
    from app.application.candidates.display import build_candidate_display_card

    candidate_rows = (
        base.filter(
            or_(*[SourceItem.raw_metadata_json.like(f"%{m}%") for m in _SUMMARY_MARKERS])
        )
        .order_by(SourceItem.first_seen_at.desc(), SourceItem.id.desc())
        .limit(_TOP_ITEMS_LIMIT)
        .all()
    )

    top_items: list[DailyDigestItem] = []
    for it in candidate_rows:
        card = build_candidate_display_card(it)
        top_items.append(
            DailyDigestItem(
                item_id=it.id,
                title=card.title,
                zh_preview=card.primary_text if card.uses_zh_one_liner else None,
                source_key=it.source_key,
                insight_card_id=it.insight_card_id,
            )
        )

    return DailyDigestView(
        date_label=day_start.strftime("%Y-%m-%d"),
        new_items_count=new_items_count,
        summarized_count=summarized_count,
        card_count=card_count,
        source_count=source_count,
        top_items=top_items,
    )


# ── Daily briefing (the readable "今日新增报告") ──────────────────────────────
# A fuller, read-only view than the sidebar digest: lists ALL of today's newly
# discovered items (capped), grouped by source, each with its Chinese one-liner
# (or title), discovery time and read links. No LLM, no writes — this is the
# deterministic "new-items report" that lets a user actually read what's new.

DEFAULT_BRIEFING_MAX = get_daily_scope_settings().briefing_limit


@dataclass(frozen=True)
class DailyBriefingItem:
    item_id: int
    title: str
    zh_preview: str | None
    has_summary: bool
    url: str | None
    time_label: str
    insight_card_id: int | None


@dataclass(frozen=True)
class DailyBriefingGroup:
    source_key: str
    source_name: str
    items: list[DailyBriefingItem]


@dataclass(frozen=True)
class DailyBriefingView:
    date_label: str
    new_items_count: int   # total new today (may exceed shown if truncated)
    shown_count: int
    summarized_count: int  # shown items that have a readable Chinese one-liner
    source_count: int
    groups: list[DailyBriefingGroup]
    truncated: bool


def build_daily_briefing(
    db, *, now: datetime | None = None, max_items: int = DEFAULT_BRIEFING_MAX
) -> DailyBriefingView:
    """Build a read-only briefing of today's newly discovered items.

    Groups by source, newest-first within each source. Read-only; no LLM.
    Unlike the sidebar digest, this includes items that are not yet summarized
    (falling back to their title) so the user sees everything new.
    """
    if now is None:
        now = datetime.utcnow()
    day_start = _start_of_utc_day(now)

    base = recent_valid_items_query(db, now=now)
    new_items_count = base.count()

    rows = (
        base.order_by(
            SourceItem.first_seen_at.desc(),
            SourceItem.id.desc(),
        )
        .limit(max_items)
        .all()
    )

    keys = {row.source_key for row in rows}
    source_names = {
        source.source_key: source.name
        for source in db.query(Source).filter(Source.source_key.in_(keys)).all()
    } if keys else {}

    from app.application.candidates.display import build_candidate_display_card

    groups_map: dict[str, list[DailyBriefingItem]] = {}
    summarized = 0
    for r in rows:
        card = build_candidate_display_card(r)
        zh = card.primary_text if card.uses_zh_one_liner else None
        if card.uses_zh_one_liner:
            summarized += 1
        groups_map.setdefault(r.source_key, []).append(
            DailyBriefingItem(
                item_id=r.id,
                title=card.title,
                zh_preview=zh,
                has_summary=card.uses_zh_one_liner,
                url=r.url,
                time_label=card.time_label,
                insight_card_id=r.insight_card_id,
            )
        )

    groups = [
        DailyBriefingGroup(
            source_key=k,
            source_name=source_names.get(k, k),
            items=v,
        )
        for k, v in groups_map.items()
    ]

    return DailyBriefingView(
        date_label=day_start.strftime("%Y-%m-%d"),
        new_items_count=new_items_count,
        shown_count=len(rows),
        summarized_count=summarized,
        source_count=len(groups),
        groups=groups,
        truncated=new_items_count > len(rows),
    )
