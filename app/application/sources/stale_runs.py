"""Stale running FetchRun diagnostics for V1.0-beta.1.

Provides read-only logic to identify FetchRun rows that are stuck in the
``running`` state for longer than a configurable threshold. Such rows cause
due-source computation to keep reporting ``already_running`` for the affected
source, so the source is silently skipped on every "update today radar" cycle.

This module is DIAGNOSTIC ONLY. It is strictly read-only: it never modifies
FetchRun status (no auto-fail, no retry), never writes to the database, never
schedules background tasks, never triggers fetches, and never calls LLM
services.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from app.models import FetchRun

# Default stale-running threshold in minutes.
DEFAULT_STALE_RUNNING_MINUTES = 120

# Valid bounds for the configurable threshold.
MIN_STALE_RUNNING_MINUTES = 10
MAX_STALE_RUNNING_MINUTES = 10080  # 7 days

# Reason codes for StaleFetchRunDecision.reason.
REASON_RUNNING_TOO_LONG = "running_too_long"
REASON_MISSING_STARTED_AT = "missing_started_at"


def get_stale_running_threshold_minutes() -> int:
    """Return the stale-running threshold in minutes.

    Reads from the ``RADAR_STALE_RUNNING_MINUTES`` env var.
    Falls back to ``DEFAULT_STALE_RUNNING_MINUTES`` (120) when unset, invalid,
    below ``MIN_STALE_RUNNING_MINUTES`` (10), or above
    ``MAX_STALE_RUNNING_MINUTES`` (10080 = 7 days).
    """
    raw = os.getenv("RADAR_STALE_RUNNING_MINUTES")
    if raw is None:
        return DEFAULT_STALE_RUNNING_MINUTES
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_STALE_RUNNING_MINUTES
    if value < MIN_STALE_RUNNING_MINUTES or value > MAX_STALE_RUNNING_MINUTES:
        return DEFAULT_STALE_RUNNING_MINUTES
    return value


@dataclass(frozen=True)
class StaleFetchRunDecision:
    """A single stale running FetchRun's diagnostic result."""

    run_id: int
    source_key: str
    status: str
    started_at: datetime | None
    finished_at: datetime | None
    age_minutes: int | None
    threshold_minutes: int
    reason: str
    items_found: int | None = None
    items_new: int | None = None
    items_updated: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class StaleFetchRunReport:
    """Aggregated stale running FetchRun diagnostic report."""

    generated_at: datetime
    threshold_minutes: int
    total_running: int
    stale_count: int
    stale_runs: list[StaleFetchRunDecision]
    affected_source_keys: list[str]


def build_stale_fetch_run_report(
    db,
    *,
    now: datetime | None = None,
    threshold_minutes: int | None = None,
) -> StaleFetchRunReport:
    """Compute a read-only report of stale running FetchRun rows.

    A running FetchRun is considered stale when:
    - ``started_at`` is None (reason ``missing_started_at``), or
    - ``now - started_at`` exceeds ``threshold_minutes``
      (reason ``running_too_long``).

    This function only queries the database. It never writes, never schedules
    background work, and never modifies FetchRun status.
    """
    if now is None:
        now = datetime.utcnow()
    if threshold_minutes is None:
        threshold_minutes = get_stale_running_threshold_minutes()

    running_runs = (
        db.query(FetchRun)
        .filter(FetchRun.status == "running")
        .order_by(FetchRun.started_at.asc().nullsfirst(), FetchRun.id.asc())
        .all()
    )

    total_running = len(running_runs)
    stale_runs: list[StaleFetchRunDecision] = []
    affected: set[str] = set()

    for run in running_runs:
        started_at = run.started_at
        if started_at is None:
            reason = REASON_MISSING_STARTED_AT
            age_minutes = None
        else:
            age_minutes = int((now - started_at).total_seconds() // 60)
            if age_minutes <= threshold_minutes:
                continue
            reason = REASON_RUNNING_TOO_LONG

        stale_runs.append(
            StaleFetchRunDecision(
                run_id=run.id,
                source_key=run.source_key,
                status=run.status,
                started_at=started_at,
                finished_at=run.finished_at,
                age_minutes=age_minutes,
                threshold_minutes=threshold_minutes,
                reason=reason,
                items_found=run.items_found,
                items_new=run.items_new,
                items_updated=run.items_updated,
                error_message=run.error_message,
            )
        )
        affected |= {run.source_key}

    return StaleFetchRunReport(
        generated_at=now,
        threshold_minutes=threshold_minutes,
        total_running=total_running,
        stale_count=len(stale_runs),
        stale_runs=stale_runs,
        affected_source_keys=sorted(affected),
    )
