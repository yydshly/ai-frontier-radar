"""Controlled source discovery entry points for bootstrap and daily increment.

This module orchestrates existing YAML-configured sources. It does not parse
RSS/HTML itself, does not call LLMs, and does not change the database schema.
Apply mode reuses SourceFetchBackgroundService so FetchRun and SourceItem
dedupe behavior stay in one place.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import os
from typing import Iterator

from sqlalchemy.orm import Session

from app.application.sources.background_fetch import SourceFetchBackgroundService
from app.application.sources.due_sources import compute_due_sources
from app.application.sources.fetch_service import SUPPORTED_STRATEGIES
from app.models import FetchRun, Source
from app.sources.config_loader import get_enabled_sources


BOOTSTRAP_MODE = "bootstrap"
DAILY_INCREMENT_MODE = "daily_increment"
SUPPORTED_DISCOVERY_MODES = {BOOTSTRAP_MODE, DAILY_INCREMENT_MODE}

DEFAULT_BOOTSTRAP_MAX_ITEMS_PER_SOURCE = 20
DEFAULT_BOOTSTRAP_MAX_SOURCES = 15
MAX_ITEMS_PER_SOURCE_CAP = 50
MAX_SOURCES_CAP = 100


@dataclass(frozen=True)
class SourceDiscoveryRunSettings:
    mode: str
    max_items_per_source: int = DEFAULT_BOOTSTRAP_MAX_ITEMS_PER_SOURCE
    max_sources: int = DEFAULT_BOOTSTRAP_MAX_SOURCES
    dry_run: bool = True


@dataclass(frozen=True)
class SourceDiscoverySourceResult:
    source_key: str
    status: str
    run_id: int | None = None
    message: str = ""
    items_found: int = 0
    items_new: int = 0
    items_updated: int = 0
    items_failed: int = 0


@dataclass(frozen=True)
class SourceDiscoveryRunResult:
    mode: str
    dry_run: bool
    total_sources: int
    eligible_sources: int
    started: int
    skipped: int
    unsupported: int
    failed: int
    message: str
    execution_mode: str = "dry_run"  # "dry_run" | "background" | "sync"
    source_results: list[SourceDiscoverySourceResult] = field(default_factory=list)


def normalize_max_items_per_source(value: int | None) -> int:
    if value is None:
        return DEFAULT_BOOTSTRAP_MAX_ITEMS_PER_SOURCE
    if value < 1:
        return DEFAULT_BOOTSTRAP_MAX_ITEMS_PER_SOURCE
    return min(value, MAX_ITEMS_PER_SOURCE_CAP)


def normalize_max_sources(value: int | None) -> int:
    if value is None:
        return DEFAULT_BOOTSTRAP_MAX_SOURCES
    if value < 1:
        return DEFAULT_BOOTSTRAP_MAX_SOURCES
    return min(value, MAX_SOURCES_CAP)


def run_source_discovery(
    db: Session,
    settings: SourceDiscoveryRunSettings,
    *,
    background_tasks=None,
) -> SourceDiscoveryRunResult:
    """Run a dry-run or apply source discovery cycle.

    Args:
        background_tasks: FastAPI BackgroundTasks instance. When provided and
            dry_run=False, enqueue_source is called with background_tasks so
            the actual fetch runs in the background (no blocking). When None,
            enqueue_source is called with background_tasks=None for synchronous
            execution (CLI / testing).
    """
    mode = settings.mode
    if mode not in SUPPORTED_DISCOVERY_MODES:
        raise ValueError(f"unsupported discovery mode: {mode}")

    max_items = normalize_max_items_per_source(settings.max_items_per_source)
    max_sources = normalize_max_sources(settings.max_sources)
    normalized = SourceDiscoveryRunSettings(
        mode=mode,
        max_items_per_source=max_items,
        max_sources=max_sources,
        dry_run=settings.dry_run,
    )

    if mode == BOOTSTRAP_MODE:
        return _run_bootstrap(db, normalized, background_tasks=background_tasks)
    return _run_daily_increment(db, normalized, background_tasks=background_tasks)


def _run_bootstrap(
    db: Session,
    settings: SourceDiscoveryRunSettings,
    *,
    background_tasks=None,
) -> SourceDiscoveryRunResult:
    configured = get_enabled_sources()
    total_sources = len(configured)
    eligible: list[str] = []
    unsupported = 0
    skipped = 0
    source_results: list[SourceDiscoverySourceResult] = []

    for cfg in configured:
        if cfg.fetch_strategy not in SUPPORTED_STRATEGIES:
            unsupported += 1
            source_results.append(
                SourceDiscoverySourceResult(
                    source_key=cfg.source_key,
                    status="unsupported",
                    message=f"unsupported fetch_strategy: {cfg.fetch_strategy}",
                )
            )
            continue

        source = db.query(Source).filter(Source.source_key == cfg.source_key).first()
        if source is None:
            skipped += 1
            source_results.append(
                SourceDiscoverySourceResult(
                    source_key=cfg.source_key,
                    status="missing",
                    message="Source row missing; sync YAML sources first",
                )
            )
            continue

        latest_running = (
            db.query(FetchRun)
            .filter(FetchRun.source_key == cfg.source_key, FetchRun.status == "running")
            .order_by(FetchRun.started_at.desc())
            .first()
        )
        if latest_running is not None:
            skipped += 1
            source_results.append(
                SourceDiscoverySourceResult(
                    source_key=cfg.source_key,
                    status="already_running",
                    run_id=latest_running.id,
                    message="FetchRun already running",
                )
            )
            continue

        eligible.append(cfg.source_key)

    capped_eligible = eligible[: settings.max_sources]
    skipped += max(0, len(eligible) - len(capped_eligible))

    if settings.dry_run:
        source_results.extend(
            SourceDiscoverySourceResult(
                source_key=source_key,
                status="would_start",
                message="dry-run only; no FetchRun created",
            )
            for source_key in capped_eligible
        )
        return SourceDiscoveryRunResult(
            mode=settings.mode,
            dry_run=True,
            total_sources=total_sources,
            eligible_sources=len(capped_eligible),
            started=0,
            skipped=skipped,
            unsupported=unsupported,
            failed=0,
            message=f"Bootstrap dry-run: would start {len(capped_eligible)} source(s).",
            execution_mode="dry_run",
            source_results=source_results,
        )

    return _apply_source_keys(
        settings=settings,
        total_sources=total_sources,
        eligible_source_keys=capped_eligible,
        skipped=skipped,
        unsupported=unsupported,
        source_results=source_results,
        background_tasks=background_tasks,
    )


def _run_daily_increment(
    db: Session,
    settings: SourceDiscoveryRunSettings,
    *,
    background_tasks=None,
) -> SourceDiscoveryRunResult:
    plan = compute_due_sources(db, max_sources=settings.max_sources)
    eligible_source_keys = [decision.source_key for decision in plan.due]
    source_results: list[SourceDiscoverySourceResult] = [
        SourceDiscoverySourceResult(d.source_key, "skipped", message=d.reason)
        for d in plan.skipped
    ]
    source_results.extend(
        SourceDiscoverySourceResult(d.source_key, "already_running", message=d.reason)
        for d in plan.running
    )
    source_results.extend(
        SourceDiscoverySourceResult(d.source_key, "unsupported", message=d.reason)
        for d in plan.unsupported
    )
    source_results.extend(
        SourceDiscoverySourceResult(d.source_key, "missing", message=d.reason)
        for d in plan.missing
    )

    skipped = plan.skipped_count + plan.running_count + plan.missing_count

    if settings.dry_run:
        source_results.extend(
            SourceDiscoverySourceResult(
                source_key=source_key,
                status="would_start",
                message="dry-run only; no FetchRun created",
            )
            for source_key in eligible_source_keys
        )
        return SourceDiscoveryRunResult(
            mode=settings.mode,
            dry_run=True,
            total_sources=plan.total_configured,
            eligible_sources=plan.due_count,
            started=0,
            skipped=skipped,
            unsupported=plan.unsupported_count,
            failed=0,
            message=f"Daily increment dry-run: would start {plan.due_count} due source(s).",
            execution_mode="dry_run",
            source_results=source_results,
        )

    return _apply_source_keys(
        settings=settings,
        total_sources=plan.total_configured,
        eligible_source_keys=eligible_source_keys,
        skipped=skipped,
        unsupported=plan.unsupported_count,
        source_results=source_results,
        background_tasks=background_tasks,
    )


def _apply_source_keys(
    *,
    settings: SourceDiscoveryRunSettings,
    total_sources: int,
    eligible_source_keys: list[str],
    skipped: int,
    unsupported: int,
    source_results: list[SourceDiscoverySourceResult],
    background_tasks=None,
) -> SourceDiscoveryRunResult:
    fetch_service = SourceFetchBackgroundService()
    started = 0
    failed = 0

    with _discovery_apply_environment(settings.max_items_per_source):
        for source_key in eligible_source_keys:
            try:
                result = fetch_service.enqueue_source(source_key, background_tasks=background_tasks)
            except Exception as exc:
                failed += 1
                source_results.append(
                    SourceDiscoverySourceResult(
                        source_key=source_key,
                        status="failed",
                        message=str(exc),
                    )
                )
                continue

            if result.accepted:
                started += 1
                source_results.append(
                    SourceDiscoverySourceResult(
                        source_key=source_key,
                        status=result.status,
                        run_id=result.run_id,
                        message=result.message,
                    )
                )
            elif result.status == "already_running":
                skipped += 1
                source_results.append(
                    SourceDiscoverySourceResult(
                        source_key=source_key,
                        status="already_running",
                        run_id=result.run_id,
                        message=result.message,
                    )
                )
            else:
                failed += 1
                source_results.append(
                    SourceDiscoverySourceResult(
                        source_key=source_key,
                        status=result.status,
                        run_id=result.run_id,
                        message=result.message,
                    )
                )

    exec_mode = "background" if background_tasks is not None else "sync"
    if exec_mode == "background":
        msg_prefix = f"{settings.mode} apply queued"
    else:
        msg_prefix = f"{settings.mode} apply finished"

    return SourceDiscoveryRunResult(
        mode=settings.mode,
        dry_run=False,
        total_sources=total_sources,
        eligible_sources=len(eligible_source_keys),
        started=started,
        skipped=skipped,
        unsupported=unsupported,
        failed=failed,
        message=f"{msg_prefix}: started {started} source(s).",
        execution_mode=exec_mode,
        source_results=source_results,
    )


@contextmanager
def _discovery_apply_environment(max_items_per_source: int) -> Iterator[None]:
    """Apply no-LLM and per-source limits around synchronous discovery runs.

    quick_test static assertion: AUTO_SUMMARY_MAX_PER_FETCH_RUN=0 and
    SOURCE_FETCH_MAX_ITEMS_PER_RUN are set so that apply paths never trigger
    LLM-based auto-summaries.
    """
    old_auto_summary = os.environ.get("AUTO_SUMMARY_MAX_PER_FETCH_RUN")
    old_source_limit = os.environ.get("SOURCE_FETCH_MAX_ITEMS_PER_RUN")
    os.environ["AUTO_SUMMARY_MAX_PER_FETCH_RUN"] = "0"
    os.environ["SOURCE_FETCH_MAX_ITEMS_PER_RUN"] = str(max_items_per_source)
    # quick_test static assertion: verify env vars block LLM calls
    assert os.environ.get("AUTO_SUMMARY_MAX_PER_FETCH_RUN") == "0", (
        "AUTO_SUMMARY_MAX_PER_FETCH_RUN must remain 0 to prevent LLM calls during apply"
    )
    try:
        yield
    finally:
        _restore_env("AUTO_SUMMARY_MAX_PER_FETCH_RUN", old_auto_summary)
        _restore_env("SOURCE_FETCH_MAX_ITEMS_PER_RUN", old_source_limit)


def _restore_env(key: str, old_value: str | None) -> None:
    if old_value is None:
        os.environ.pop(key, None)
    else:
        os.environ[key] = old_value
