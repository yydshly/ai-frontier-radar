"""Shared query policy for user-facing today-radar content."""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models import Source, SourceItem


DEFAULT_DAILY_HOURS = 24


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
