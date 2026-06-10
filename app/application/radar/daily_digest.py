"""Read-only daily digest aggregation for the today-radar (P-003 step 1).

Aggregates *today's* newly discovered SourceItems into a compact "今日编译概览"
summary for the radar sidebar. This is the data foundation for the future
"今日核心报告卡片"; it does NOT call any LLM and does NOT write to the database.

Phase boundaries:
- Phase C (this module): read-only aggregation + counts + a few top items.
- Phase D (later): LLM core summary generation (cost-gated, explicit).
- Phase E (later): voice broadcast (TTS, optional / toggleable).

"Today" = the current UTC calendar day [00:00, now]. An item counts as "today"
by its ``first_seen_at`` (first discovery), matching how new items enter.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_

from app.models import SourceItem

# Markers that indicate a SourceItem already carries a (Chinese) summary.
_SUMMARY_MARKERS = ('"zh_one_liner"', '"summary_zh"', '"auto_summary"')

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

    base = db.query(SourceItem).filter(SourceItem.first_seen_at >= day_start)

    new_items_count = base.count()

    summarized_count = (
        base.filter(
            or_(*[SourceItem.raw_metadata_json.like(f"%{m}%") for m in _SUMMARY_MARKERS])
        ).count()
    )

    card_count = base.filter(SourceItem.insight_card_id.isnot(None)).count()

    source_count = (
        db.query(SourceItem.source_key)
        .filter(SourceItem.first_seen_at >= day_start)
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
