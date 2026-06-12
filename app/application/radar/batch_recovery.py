"""Recovery for interrupted background batches (P4).

Summary and insight batches run via FastAPI BackgroundTasks, whose in-memory
queue is lost on process restart. The *per-item* state, however, is already
persisted:

- summaries: ``raw_metadata_json[radar_summary_batch_status]`` = queued|running
  (plus ``radar_summary_batch_updated_at``).
- insights:  ``SourceItem.status`` = "compiling" (plus ``SourceItem.updated_at``).

So an item left in an in-progress state with no live worker is an *interrupted*
task. This module detects those (guarded by a staleness threshold so a
genuinely-running worker is never disturbed) and re-runs them — mirroring the
explicit "resume" the audio jobs already offer. It does NOT run on startup and
adds no new LLM gating: re-running goes through the same background runners.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func

from app.db import SessionLocal
from app.models import SourceItem
from app.application.radar.background_summary import (
    SUMMARY_BATCH_STATUS_KEY,
    SUMMARY_BATCH_UPDATED_AT_KEY,
    run_summary_batch_in_background,
)
from app.application.source_items.background_compile import (
    run_source_item_compile_in_background,
)

# In-progress states only count as "interrupted" once they have been untouched
# for this long, so an actively-running worker is never preempted. Summary /
# insight items normally reach a terminal state within seconds.
DEFAULT_STALE_MINUTES = 15

_SUMMARY_IN_PROGRESS = ("queued", "running")


@dataclass(frozen=True)
class InterruptedBatchCounts:
    summary: int = 0
    insight: int = 0

    @property
    def total(self) -> int:
        return self.summary + self.insight

    @property
    def any(self) -> bool:
        return self.total > 0


@dataclass(frozen=True)
class ResumeResult:
    summary: int = 0
    insight: int = 0

    @property
    def total(self) -> int:
        return self.summary + self.insight


def _stale_minutes() -> int:
    """Staleness threshold (minutes); override with RADAR_BATCH_STALE_MINUTES."""
    raw = os.getenv("RADAR_BATCH_STALE_MINUTES")
    if raw is None:
        return DEFAULT_STALE_MINUTES
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_STALE_MINUTES
    return value if 0 <= value <= 1440 else DEFAULT_STALE_MINUTES


# Recovery only looks back this many days. Interrupted summary/insight tasks are
# always enqueued for the increment / recent fetches, so bounding by
# first_seen_at (indexed) lets the detection use the index instead of scanning
# the whole table with json_extract on every page load. A task older than this is
# effectively abandoned (re-summarized via the normal increment flow).
_RECOVERY_LOOKBACK_DAYS = 7


def _recovery_lookback_cutoff() -> datetime:
    raw = os.getenv("RADAR_BATCH_RECOVERY_LOOKBACK_DAYS")
    try:
        days = int(raw) if raw is not None else _RECOVERY_LOOKBACK_DAYS
    except (TypeError, ValueError):
        days = _RECOVERY_LOOKBACK_DAYS
    if not (1 <= days <= 365):
        days = _RECOVERY_LOOKBACK_DAYS
    return datetime.utcnow() - timedelta(days=days)


def _summary_status_expr():
    return func.json_extract(
        SourceItem.raw_metadata_json, f"$.{SUMMARY_BATCH_STATUS_KEY}"
    )


def _summary_updated_expr():
    return func.json_extract(
        SourceItem.raw_metadata_json, f"$.{SUMMARY_BATCH_UPDATED_AT_KEY}"
    )


def find_interrupted_summary_ids(db, *, stale_minutes: int) -> list[int]:
    """Ids of summary items stuck in queued/running past the staleness window.

    The batch status/timestamp live inside raw_metadata_json; json_extract keeps
    the filtering in SQL so we never scan full rows. Items with no recorded
    timestamp are treated as interrupted (a worker that died right after enqueue
    may not have written one).
    """
    cutoff_iso = (datetime.utcnow() - timedelta(minutes=stale_minutes)).isoformat()
    rows = (
        db.query(SourceItem.id, _summary_updated_expr())
        # Bound by the indexed first_seen_at FIRST so json_extract only runs on
        # recent rows, not the whole table (this runs on every page load).
        .filter(SourceItem.first_seen_at >= _recovery_lookback_cutoff())
        .filter(_summary_status_expr().in_(_SUMMARY_IN_PROGRESS))
        .all()
    )
    ids: list[int] = []
    for item_id, updated_at in rows:
        # ISO-8601 strings compare lexicographically in chronological order.
        if not updated_at or str(updated_at) < cutoff_iso:
            ids.append(item_id)
    return ids


def find_interrupted_insight_ids(db, *, stale_minutes: int) -> list[int]:
    """Ids of insight items stuck in 'compiling' past the staleness window."""
    cutoff = datetime.utcnow() - timedelta(minutes=stale_minutes)
    rows = (
        db.query(SourceItem.id)
        .filter(
            SourceItem.first_seen_at >= _recovery_lookback_cutoff(),
            SourceItem.status == "compiling",
            (SourceItem.updated_at.is_(None)) | (SourceItem.updated_at < cutoff),
        )
        .all()
    )
    return [row[0] for row in rows]


def count_interrupted_batches(
    db, *, stale_minutes: int | None = None
) -> InterruptedBatchCounts:
    """Count interrupted summary + insight batch items (read-only)."""
    minutes = _stale_minutes() if stale_minutes is None else stale_minutes
    return InterruptedBatchCounts(
        summary=len(find_interrupted_summary_ids(db, stale_minutes=minutes)),
        insight=len(find_interrupted_insight_ids(db, stale_minutes=minutes)),
    )


def resume_interrupted_batches(
    background_tasks, *, stale_minutes: int | None = None
) -> ResumeResult:
    """Re-run interrupted summary + insight batches in the background.

    Detection is read-only; the actual work is dispatched to the same background
    runners used by the original enqueue paths. Returns how many items of each
    kind were dispatched.
    """
    minutes = _stale_minutes() if stale_minutes is None else stale_minutes
    db = SessionLocal()
    try:
        summary_ids = find_interrupted_summary_ids(db, stale_minutes=minutes)
        insight_ids = find_interrupted_insight_ids(db, stale_minutes=minutes)
    finally:
        db.close()

    if summary_ids:
        background_tasks.add_task(run_summary_batch_in_background, summary_ids)
    for item_id in insight_ids:
        background_tasks.add_task(run_source_item_compile_in_background, item_id)

    return ResumeResult(summary=len(summary_ids), insight=len(insight_ids))
