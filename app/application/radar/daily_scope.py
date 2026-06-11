"""Shared query policy for user-facing today-radar content."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Source, SourceItem


DEFAULT_DAILY_HOURS = 24

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
