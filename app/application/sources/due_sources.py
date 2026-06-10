"""Due-source computation service for V1.0-beta.1.

Provides read-only logic to determine which radar sources are due for a fetch
run this cycle, which are skipped and why, and which are in special states
(running / unsupported / missing).

This module does NOT:
- Trigger any fetches
- Write to the database
- Enqueue background tasks
- Call LLM services
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any

# Supported fetch strategies for due-source computation.
SUPPORTED_FETCH_STRATEGIES: frozenset[str] = frozenset({"rss", "html_index"})

# Reason codes for DueSourceDecision.reason.
REASON_NEVER_FETCHED = "never_fetched"
REASON_INTERVAL_ELAPSED = "interval_elapsed"
REASON_NOT_DUE_YET = "not_due_yet"
REASON_ALREADY_RUNNING = "already_running"
REASON_UNSUPPORTED_STRATEGY = "unsupported_strategy"
REASON_MISSING_SOURCE_RECORD = "missing_source_record"
REASON_DISABLED = "disabled"
REASON_MAX_SOURCES_LIMIT = "max_sources_limit"


def get_default_fetch_interval_hours() -> int:
    """Return the default fetch interval in hours.

    Reads from RADAR_DEFAULT_FETCH_INTERVAL_HOURS env var.
    Falls back to 24 if unset, invalid, <= 0, or > 30 days.
    """
    raw = os.getenv("RADAR_DEFAULT_FETCH_INTERVAL_HOURS")
    if raw is None:
        return 24
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 24
    if value <= 0 or value > 24 * 30:
        return 24
    return value


def get_source_fetch_interval_hours(config_source: object | None) -> int:
    """Return the fetch interval for a given SourceConfig, or the default.

    Looks for ``fetch_interval_hours`` then ``interval_hours`` attributes.
    Returns the default if the attribute is missing or invalid.
    """
    default = get_default_fetch_interval_hours()
    if config_source is None:
        return default

    value = getattr(config_source, "fetch_interval_hours", None)
    if value is None:
        value = getattr(config_source, "interval_hours", None)
    if value is None:
        return default

    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default

    if parsed <= 0 or parsed > 24 * 30:
        return default
    return parsed


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DueSourceDecision:
    """A single source's due-source computation result."""

    source_key: str
    source_name: str
    status: str  # "due" | "skipped" | "running" | "unsupported" | "missing"
    reason: str
    fetch_strategy: str | None = None
    fetch_interval_hours: int | None = None
    latest_run_status: str | None = None
    latest_run_started_at: datetime | None = None
    latest_run_finished_at: datetime | None = None
    next_due_at: datetime | None = None
    source_id: int | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class DueSourcePlan:
    """Aggregated result of due-source computation across all radar sources."""

    generated_at: datetime
    total_configured: int
    due: list[DueSourceDecision] = field(default_factory=list)
    skipped: list[DueSourceDecision] = field(default_factory=list)
    running: list[DueSourceDecision] = field(default_factory=list)
    unsupported: list[DueSourceDecision] = field(default_factory=list)
    missing: list[DueSourceDecision] = field(default_factory=list)

    @property
    def due_count(self) -> int:
        return len(self.due)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)

    @property
    def running_count(self) -> int:
        return len(self.running)

    @property
    def unsupported_count(self) -> int:
        return len(self.unsupported)

    @property
    def missing_count(self) -> int:
        return len(self.missing)


# ---------------------------------------------------------------------------
# Core service
# ---------------------------------------------------------------------------


def compute_due_sources(
    db,
    *,
    now: datetime | None = None,
    max_sources: int | None = None,
) -> DueSourcePlan:
    """Compute which configured radar sources are due for fetching this cycle.

    This function is fully read-only — it does not write to the database or
    trigger any side-effects.

    Parameters
    ----------
    db:
        SQLAlchemy session for querying the database.
    now:
        Optional fixed timestamp to use as "now". Defaults to datetime.utcnow().
        Exists to make the function deterministic in tests.
    max_sources:
        Optional cap on the number of sources returned as ``due``.
        When set, sources beyond the cap are moved to ``skipped`` with reason
        ``max_sources_limit``. ``skipped``, ``running``, ``unsupported``, and
        ``missing`` lists are unaffected.

    Returns
    -------
    DueSourcePlan
        Structured result containing due / skipped / running / unsupported /
        missing buckets, each as a list of DueSourceDecision objects.
    """
    if now is None:
        now = datetime.utcnow()

    # Import here to keep module boundaries clean.
    from app.models import FetchRun, Source
    from app.sources.config_loader import get_enabled_sources

    configured_sources = get_enabled_sources()
    total_configured = len(configured_sources)

    due: list[DueSourceDecision] = []
    skipped: list[DueSourceDecision] = []
    running: list[DueSourceDecision] = []
    unsupported: list[DueSourceDecision] = []
    missing: list[DueSourceDecision] = []

    for cfg in configured_sources:
        source_key = cfg.source_key
        source_name = cfg.name
        fetch_strategy = cfg.fetch_strategy
        interval_hours = get_source_fetch_interval_hours(cfg)

        # 1. Check DB Source record exists.
        db_source: Source | None = db.query(Source).filter_by(source_key=source_key).first()
        if db_source is None:
            missing.append(
                DueSourceDecision(
                    source_key=source_key,
                    source_name=source_name,
                    status="missing",
                    reason=REASON_MISSING_SOURCE_RECORD,
                    fetch_strategy=fetch_strategy,
                    fetch_interval_hours=interval_hours,
                )
            )
            continue

        source_id: int | None = db_source.id

        # 2. Check fetch strategy support.
        if fetch_strategy not in SUPPORTED_FETCH_STRATEGIES:
            unsupported.append(
                DueSourceDecision(
                    source_key=source_key,
                    source_name=source_name,
                    status="unsupported",
                    reason=REASON_UNSUPPORTED_STRATEGY,
                    fetch_strategy=fetch_strategy,
                    fetch_interval_hours=interval_hours,
                    source_id=source_id,
                )
            )
            continue

        # 3. Get latest FetchRun for this source.
        latest_run: FetchRun | None = (
            db.query(FetchRun)
            .filter(FetchRun.source_key == source_key)
            .order_by(FetchRun.started_at.desc())
            .first()
        )

        # 4. Check if a FetchRun is currently running.
        if latest_run is not None and latest_run.status == "running":
            running.append(
                DueSourceDecision(
                    source_key=source_key,
                    source_name=source_name,
                    status="running",
                    reason=REASON_ALREADY_RUNNING,
                    fetch_strategy=fetch_strategy,
                    fetch_interval_hours=interval_hours,
                    latest_run_status="running",
                    latest_run_started_at=latest_run.started_at,
                    source_id=source_id,
                )
            )
            continue

        # 5. No prior FetchRun → due immediately.
        if latest_run is None:
            due.append(
                DueSourceDecision(
                    source_key=source_key,
                    source_name=source_name,
                    status="due",
                    reason=REASON_NEVER_FETCHED,
                    fetch_strategy=fetch_strategy,
                    fetch_interval_hours=interval_hours,
                    source_id=source_id,
                )
            )
            continue

        # 6. Has prior FetchRun — check interval.
        latest_status: str | None = latest_run.status
        latest_started: datetime | None = latest_run.started_at
        latest_finished: datetime | None = latest_run.finished_at

        if latest_started is None:
            # Malformed record — count as never fetched.
            due.append(
                DueSourceDecision(
                    source_key=source_key,
                    source_name=source_name,
                    status="due",
                    reason=REASON_NEVER_FETCHED,
                    fetch_strategy=fetch_strategy,
                    fetch_interval_hours=interval_hours,
                    latest_run_status=latest_status,
                    source_id=source_id,
                )
            )
            continue

        elapsed = now - latest_started
        interval_delta = timedelta(hours=interval_hours)

        if elapsed >= interval_delta:
            due.append(
                DueSourceDecision(
                    source_key=source_key,
                    source_name=source_name,
                    status="due",
                    reason=REASON_INTERVAL_ELAPSED,
                    fetch_strategy=fetch_strategy,
                    fetch_interval_hours=interval_hours,
                    latest_run_status=latest_status,
                    latest_run_started_at=latest_started,
                    latest_run_finished_at=latest_finished,
                    source_id=source_id,
                )
            )
        else:
            next_due = latest_started + interval_delta
            skipped.append(
                DueSourceDecision(
                    source_key=source_key,
                    source_name=source_name,
                    status="skipped",
                    reason=REASON_NOT_DUE_YET,
                    fetch_strategy=fetch_strategy,
                    fetch_interval_hours=interval_hours,
                    latest_run_status=latest_status,
                    latest_run_started_at=latest_started,
                    latest_run_finished_at=latest_finished,
                    next_due_at=next_due,
                    source_id=source_id,
                )
            )

    # 7. Apply max_sources cap.
    if max_sources is not None and max_sources >= 0 and len(due) > max_sources:
        overflow = due[max_sources:]
        due = due[:max_sources]
        for decision in overflow:
            skipped.append(
                replace(decision, status="skipped", reason=REASON_MAX_SOURCES_LIMIT)
            )

    return DueSourcePlan(
        generated_at=now,
        total_configured=total_configured,
        due=due,
        skipped=skipped,
        running=running,
        unsupported=unsupported,
        missing=missing,
    )
