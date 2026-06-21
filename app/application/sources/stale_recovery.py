"""Auto-recovery for stale ``running`` FetchRuns.

This is the WRITE counterpart to the read-only ``stale_runs`` diagnostics. A
FetchRun stuck in ``running`` (e.g. the worker died mid-fetch) makes due-source
computation keep reporting ``already_running``, so that source is silently
skipped on every cycle. Releasing such rows to ``failed`` lets the next cycle
re-fetch the source.

Mirrors scripts/mark_stale_fetch_runs_failed.py (same ``failed`` status +
``[stale-timeout]`` marker) but is callable from the daily cycle so recovery is
automatic, not manual.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from app.models import FetchRun
from app.application.sources.stale_runs import get_stale_running_threshold_minutes


def release_stale_running_fetch_runs(
    db,
    *,
    threshold_minutes: int | None = None,
    now: datetime | None = None,
) -> list[dict]:
    """Mark FetchRuns stuck in ``running`` past the threshold as ``failed``.

    Returns a list of {run_id, source_key, age_minutes} for the released rows.
    Commits only when something was released.
    """
    now = now or datetime.utcnow()
    threshold = (
        threshold_minutes
        if threshold_minutes is not None
        else get_stale_running_threshold_minutes()
    )
    cutoff = now - timedelta(minutes=threshold)

    stale = (
        db.query(FetchRun)
        .filter(FetchRun.status == "running", FetchRun.started_at < cutoff)
        .all()
    )
    released: list[dict] = []
    for run in stale:
        age_min = (
            (now - run.started_at).total_seconds() / 60.0
            if run.started_at is not None
            else None
        )
        run.status = "failed"
        run.finished_at = now
        run.updated_at = now
        age_str = f"{age_min:.0f}" if age_min is not None else "unknown"
        run.error_message = (
            f"[stale-timeout] auto-released after {age_str} minutes running "
            f"(threshold={threshold}min)."
        )
        db.add(run)
        released.append(
            {"run_id": run.id, "source_key": run.source_key, "age_minutes": age_min}
        )
    if released:
        db.commit()
    return released
