"""Shared query policy for user-facing today-radar content."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Source, SourceItem


DEFAULT_DAILY_HOURS = 24


def daily_anchor(
    now: datetime | None = None,
    *,
    anchor_hour: int | None = None,
    tz_offset_hours: int | None = None,
) -> datetime:
    """Return the most recent daily anchor (local ``anchor_hour``) at-or-before
    ``now``, as a naive UTC datetime — the increment baseline.

    "Today's increment" = SourceItems with ``first_seen_at >= daily_anchor(now)``.
    Deterministic (no persistence): if local now is before today's anchor hour,
    the anchor is yesterday's. Defaults come from daily-scope settings
    (anchor_hour=8, tz_offset=+8 / Asia-Shanghai). ``now`` is treated as naive
    UTC (matching ``SourceItem.first_seen_at``), and the result is naive UTC.
    """
    from app.application.radar.settings import get_daily_scope_settings

    settings = get_daily_scope_settings()
    hour = settings.anchor_hour if anchor_hour is None else anchor_hour
    offset = (
        settings.anchor_tz_offset_hours if tz_offset_hours is None else tz_offset_hours
    )

    now_utc = now or datetime.utcnow()
    local_now = now_utc + timedelta(hours=offset)
    local_anchor = local_now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if local_now < local_anchor:
        local_anchor -= timedelta(days=1)
    return local_anchor - timedelta(hours=offset)

# Canonical raw_metadata_json substrings that mark a SourceItem as already
# carrying a (Chinese) summary. Single source of truth — imported by the digest,
# the daily report and the source workspace so their "已有中文摘要" counts can
# never drift apart.
#
# Only the two keys the system actually writes to SourceItem are kept. The
# former entries "summary_zh" / "auto_summary" were ghost keys: never present in
# any SourceItem (verified 0/2706 in real data) — "summary_zh" is an
# InsightCard column, and "auto_summary" lives on FetchRun metadata, not here.
SUMMARY_MARKERS = ('"zh_one_liner"', '"zh_summary"')


def recent_valid_items_query(
    db,
    *,
    hours: int = DEFAULT_DAILY_HOURS,
    now: datetime | None = None,
):
    """Return valid items first discovered inside the rolling daily window."""
    current = now or datetime.utcnow()
    cutoff = current - timedelta(hours=hours)
    return (
        db.query(SourceItem)
        .join(Source, Source.id == SourceItem.source_id)
        .filter(
            SourceItem.first_seen_at >= cutoff,
            Source.enabled.is_(True),
            SourceItem.url.isnot(None),
            SourceItem.url != "",
            SourceItem.title.isnot(None),
            SourceItem.title != "",
        )
    )
