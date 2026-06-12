"""Background Source Fetch Service.

Provides background fetch for sources using FastAPI BackgroundTasks.
Encapsulates enqueue logic and background execution with proper DB session isolation.

Does NOT use Celery/Redis/RQ — uses FastAPI BackgroundTasks only.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
import os

from app.db import SessionLocal
from app.models import Source, FetchRun
from app.application.sources.fetch_service import (
    get_source_fetch_max_items_per_run,
    build_source_fetch_limit_metadata,
)


# Time window for duplicate-running protection (10 minutes)
_RUNNING_WINDOW_MINUTES = 10

logger = logging.getLogger(__name__)


def get_auto_summary_max_per_fetch_run() -> int:
    """Return the max number of items to auto-summarize per FetchRun.

    Controlled by AUTO_SUMMARY_MAX_PER_FETCH_RUN env var.
    Returns 5 by default, 0 means disabled, max capped at 20.
    """
    import os
    raw = os.getenv("AUTO_SUMMARY_MAX_PER_FETCH_RUN")
    if raw is None:
        return 5
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 5
    if value < 0 or value > 20:
        return 5
    return value


def _write_auto_summary_metadata(
    db,
    fetch_run: FetchRun,
    auto_summary: dict,
) -> None:
    """Append auto_summary result to FetchRun.metadata_json, preserving existing data."""
    import json as _json

    raw: dict = {}
    if fetch_run.metadata_json:
        try:
            parsed = _json.loads(fetch_run.metadata_json)
            if isinstance(parsed, dict):
                raw = parsed
        except (_json.JSONDecodeError, TypeError):
            raw = {}

    raw["auto_summary"] = auto_summary
    fetch_run.metadata_json = _json.dumps(raw, ensure_ascii=False)
    db.add(fetch_run)
    db.commit()


def _auto_generate_summaries_for_fetch_run(
    db,
    fetch_run: FetchRun,
    item_ids: list[int],
    max_items: int | None = None,
) -> None:
    """Generate Chinese summaries for new/updated SourceItems after fetch.

    This is best-effort. It must not change FetchRun.status or fail the fetch.
    """
    import json as _json

    if max_items is None:
        max_items = get_auto_summary_max_per_fetch_run()

    if max_items <= 0:
        _write_auto_summary_metadata(
            db,
            fetch_run,
            {
                "enabled": False,
                "reason": "AUTO_SUMMARY_MAX_PER_FETCH_RUN=0",
                "candidate_count": len(item_ids),
                "processed_count": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0,
                "details": [],
            },
        )
        return

    # Deduplicate while preserving order.
    seen = set()
    unique_ids = []
    for item_id in item_ids:
        if item_id in seen:
            continue
        seen.add(item_id)
        unique_ids.append(item_id)

    if not unique_ids:
        _write_auto_summary_metadata(
            db,
            fetch_run,
            {
                "enabled": True,
                "candidate_count": 0,
                "processed_count": 0,
                "success": 0,
                "skipped": 0,
                "failed": 0,
                "details": [],
            },
        )
        return

    selected_ids = unique_ids[:max_items]

    from app.models import SourceItem
    from app.application.candidates.one_liner import (
        CandidateOneLinerService,
        get_one_liner_settings,
    )

    items = (
        db.query(SourceItem)
        .filter(SourceItem.id.in_(selected_ids))
        .all()
    )

    # Preserve selected_ids order.
    item_by_id = {item.id: item for item in items}
    ordered_items = [item_by_id[item_id] for item_id in selected_ids if item_id in item_by_id]

    try:
        service = CandidateOneLinerService(
            db,
            settings=get_one_liner_settings(),
        )
        results = service.generate_for_items(
            ordered_items,
            limit=max_items,
            fill_missing_summary=True,
        )
    except Exception as exc:
        logger.exception("Auto summary failed for FetchRun(id=%s)", fetch_run.id)
        _write_auto_summary_metadata(
            db,
            fetch_run,
            {
                "enabled": True,
                "candidate_count": len(unique_ids),
                "processed_count": 0,
                "success": 0,
                "skipped": 0,
                "failed": len(selected_ids),
                "error": str(exc)[:200],
                "details": [],
            },
        )
        return

    success = sum(1 for r in results if r.status == "success")
    skipped = sum(1 for r in results if r.status == "skipped")
    failed = sum(1 for r in results if r.status == "failed")

    details = []
    for result in results[:5]:
        details.append({
            "item_id": result.item_id,
            "status": result.status,
            "error": (result.error or "")[:120],
        })

    logger.info(
        "Auto summary for FetchRun(id=%s): success=%s skipped=%s failed=%s",
        fetch_run.id,
        success,
        skipped,
        failed,
    )

    _write_auto_summary_metadata(
        db,
        fetch_run,
        {
            "enabled": True,
            "candidate_count": len(unique_ids),
            "selected_count": len(selected_ids),
            "processed_count": len(results),
            "success": success,
            "skipped": skipped,
            "failed": failed,
            "truncated": len(unique_ids) > max_items,
            "details": details,
        },
    )


@dataclass
class SourceFetchEnqueueResult:
    """Result of enqueueing a source for background fetch."""
    accepted: bool
    run_id: int | None
    status: str           # "running" | "already_running" | "not_found"
    message: str


class SourceFetchBackgroundService:
    """Service for enqueueing a source fetch to run in the background.

    Uses FastAPI BackgroundTasks. Each background task creates its own DB session.

    Idempotency: if the same source already has a running FetchRun started
    within the last 10 minutes, returns that run_id instead of creating a new one.
    """

    def enqueue_source(
        self,
        source_key: str,
        background_tasks=None,
        *,
        max_items_per_run: int | None = None,
        auto_summary_max_items: int | None = None,
    ) -> SourceFetchEnqueueResult:
        """Enqueue a source for background fetching.

        Creates a FetchRun(status=running) immediately, then either dispatches a
        background task (if background_tasks provided) or runs synchronously.

        Args:
            source_key: The source key to fetch.
            background_tasks: Optional BackgroundTasks instance from FastAPI.
                             If None, runs synchronously (suitable for scripts/tests).
            max_items_per_run: Optional per-task fetch limit override.
            auto_summary_max_items: Optional per-task auto-summary limit override.

        Returns:
            SourceFetchEnqueueResult describing what happened.
        """
        db = SessionLocal()
        try:
            source = db.query(Source).filter(Source.source_key == source_key).first()

            if not source:
                return SourceFetchEnqueueResult(
                    accepted=False,
                    run_id=None,
                    status="not_found",
                    message=f"Source '{source_key}' not found",
                )

            # Duplicate-running protection: check for existing running FetchRun
            window_start = datetime.utcnow() - timedelta(minutes=_RUNNING_WINDOW_MINUTES)
            existing_run = (
                db.query(FetchRun)
                .filter(
                    FetchRun.source_key == source_key,
                    FetchRun.status == "running",
                    FetchRun.started_at >= window_start,
                )
                .order_by(FetchRun.started_at.desc())
                .first()
            )

            if existing_run:
                return SourceFetchEnqueueResult(
                    accepted=False,
                    run_id=existing_run.id,
                    status="already_running",
                    message=f"Fetch already running (started {existing_run.started_at})",
                )

            # Create FetchRun in running state
            fetch_run = FetchRun(
                source_id=source.id,
                source_key=source_key,
                run_type="manual",
                status="running",
                started_at=datetime.utcnow(),
            )
            db.add(fetch_run)
            db.commit()
            db.refresh(fetch_run)

            if background_tasks is not None:
                # Async background execution via FastAPI BackgroundTasks
                background_tasks.add_task(
                    run_source_fetch_in_background,
                    fetch_run.id,
                    max_items_per_run,
                    auto_summary_max_items,
                )
            else:
                # Synchronous execution when no BackgroundTasks available (scripts/tests)
                run_source_fetch_in_background(
                    fetch_run.id,
                    max_items_per_run,
                    auto_summary_max_items,
                )

            return SourceFetchEnqueueResult(
                accepted=True,
                run_id=fetch_run.id,
                status="running",
                message="Fetch enqueued, running in background",
            )

        finally:
            db.close()


def run_source_fetch_in_background(
    run_id: int,
    max_items_per_run: int | None = None,
    auto_summary_max_items: int | None = None,
) -> None:
    """Background task: perform the actual source fetch.

    Creates its own DB session. Loads the FetchRun and Source, calls the
    appropriate probe (RSS or HTML index), updates FetchRun with results,
    and updates Source timestamps.

    This function is designed to be called by FastAPI BackgroundTasks.
    It never re-raises exceptions — all errors are captured and written to the DB.

    Args:
        run_id: The FetchRun ID to execute.
    """
    db = SessionLocal()
    # Initialise so exception handler can safely reference them
    fetch_run = None
    source = None
    try:
        # Load FetchRun and Source
        fetch_run = db.query(FetchRun).filter(FetchRun.id == run_id).first()
        if not fetch_run:
            return

        source = db.query(Source).filter(Source.id == fetch_run.source_id).first()
        if not source:
            # Source was deleted between enqueue and now — mark run failed
            _finish_run_as_failed(db, fetch_run, source=None, error_message=f"Source(id={fetch_run.source_id}) not found at execution time")
            return

        # S2/S3: probe by the *effective* (RSS-first) strategy. When the fallback
        # gate is on, build a reliability-ranked chain and try weaker methods if
        # the primary fails. Default (gate off) = single effective attempt,
        # identical to S2.
        from app.application.sources.effective_strategy import (
            compute_effective_strategy,
            build_strategy_chain,
            select_succeeding_probe,
            SUPPORTED_STRATEGIES,
        )
        configured_strategy = source.fetch_strategy
        effective_strategy = compute_effective_strategy(source.feed_url, source.fetch_strategy)

        fallback_enabled = os.getenv("RADAR_FETCH_FALLBACK_ENABLED", "").strip().lower() == "true"
        if fallback_enabled:
            chain = build_strategy_chain(source.feed_url, source.homepage_url, source.fetch_strategy)
        else:
            chain = [effective_strategy]
        chain = [s for s in chain if s in SUPPORTED_STRATEGIES]

        if not chain:
            _finish_run_as_failed(
                db, fetch_run, source,
                error_message=f"unsupported fetch_strategy: {effective_strategy}",
            )
            return

        # Call the appropriate probe for a given strategy.
        max_items = (
            max_items_per_run
            if max_items_per_run is not None
            else get_source_fetch_max_items_per_run()
        )

        def _run_probe(strat: str) -> dict:
            if strat == "rss":
                from app.sources.rss_probe import probe_rss_source
                return probe_rss_source(db, source, timeout_seconds=20, max_items=max_items)
            if strat == "html_index":
                from app.sources.html_index_probe import probe_html_index_source
                return probe_html_index_source(db, source, timeout_seconds=20, max_items=max_items)
            return {
                "items_found": 0, "items_new": 0, "items_updated": 0,
                "items_failed": 0,
                "error_message": f"unknown fetch_strategy: {strat}",
            }

        try:
            strategy, probe_result, strategy_attempts = select_succeeding_probe(chain, _run_probe)
        except Exception as probe_error:
            _finish_run_as_failed(
                db, fetch_run, source,
                error_message=str(probe_error),
            )
            return

        items_found = probe_result.get("items_found", 0)
        items_new = probe_result.get("items_new", 0)
        items_updated = probe_result.get("items_updated", 0)
        items_failed = probe_result.get("items_failed", 0)
        error_message = probe_result.get("error_message")

        # Collect new/seen/updated item IDs from SourceItems in the run time window
        from app.models import SourceItem
        window_start = fetch_run.started_at
        window_end = datetime.utcnow()

        all_items = (
            db.query(SourceItem)
            .filter(
                SourceItem.source_id == source.id,
                SourceItem.last_seen_at >= window_start,
                SourceItem.last_seen_at <= window_end,
            )
            .all()
        )

        new_ids = []
        seen_ids = []
        updated_ids = []

        for item in all_items:
            delta = (item.last_seen_at - item.first_seen_at).total_seconds()
            if delta < 1.0:
                new_ids.append(item.id)
            elif item.updated_at > window_start:
                updated_ids.append(item.id)
            else:
                seen_ids.append(item.id)

        # Determine final status
        if error_message:
            if items_found == 0:
                fetch_run.status = "failed"
                source.last_error_message = error_message
            else:
                fetch_run.status = "partial_failed"
                source.last_error_message = error_message
                source.last_success_at = datetime.utcnow()
        elif items_failed > 0 and items_found > items_failed:
            fetch_run.status = "partial_failed"
            fetch_run.error_message = f"{items_failed} item(s) failed"
            source.last_error_message = fetch_run.error_message
            source.last_success_at = datetime.utcnow()
        elif items_failed > 0 and items_found == items_failed:
            fetch_run.status = "failed"
            fetch_run.error_message = "All items failed"
            source.last_error_message = "All items failed"
        else:
            fetch_run.status = "success"
            source.last_error_message = None
            source.last_success_at = datetime.utcnow()

        # Update FetchRun
        import json as _json
        fetch_run.items_found = items_found
        fetch_run.items_new = items_new
        fetch_run.items_updated = items_updated
        fetch_run.items_failed = items_failed
        fetch_run.finished_at = datetime.utcnow()
        source.last_checked_at = datetime.utcnow()
        if error_message and fetch_run.status != "success":
            if not fetch_run.error_message:
                fetch_run.error_message = error_message

        # Build source_fetch_limit metadata
        source_fetch_limit = build_source_fetch_limit_metadata(
            probe_result, max_items, items_found
        )

        # Write delta, source_fetch_limit, and the actual strategy used.
        fetch_run.metadata_json = _json.dumps({
            "delta": {
                "new_ids": new_ids,
                "seen_ids": seen_ids,
                "updated_ids": updated_ids,
                "failed_urls": [],
            },
            "source_fetch_limit": source_fetch_limit,
            "fetch_strategy": {
                "configured": configured_strategy,
                "effective": effective_strategy,
                "succeeded": strategy,
                "rss_first_applied": effective_strategy != configured_strategy,
                "fallback_used": strategy != effective_strategy,
                "attempts": strategy_attempts,
            },
        }, ensure_ascii=False)

        db.commit()

        # Auto-generate Chinese summaries for new/updated items (best-effort, must not change fetch status)
        _auto_generate_summaries_for_fetch_run(
            db,
            fetch_run,
            new_ids + updated_ids,
            max_items=auto_summary_max_items,
        )

    except Exception as e:
        # All exceptions are captured — never re-raise from a background task
        try:
            _finish_run_as_failed(
                db, fetch_run, source,
                error_message=str(e),
            )
        except Exception:
            db.rollback()
    finally:
        db.close()


def _finish_run_as_failed(
    db,
    fetch_run: FetchRun,
    source: Source | None,
    error_message: str,
    source_fetch_limit: dict | None = None,
) -> None:
    """Mark a FetchRun as failed and update Source timestamps.

    Handles source=None gracefully (source may have been deleted between enqueue and now).

    Args:
        source_fetch_limit: If provided, will be written to metadata_json. If None,
            a default "not executed" limit will be written.
    """
    import json as _json
    fetch_run.status = "failed"
    fetch_run.error_message = error_message
    fetch_run.finished_at = datetime.utcnow()

    if source_fetch_limit is None:
        source_fetch_limit = {
            "max_items_per_run": get_source_fetch_max_items_per_run(),
            "truncated": False,
            "total_seen": 0,
            "processed_count": 0,
        }

    fetch_run.metadata_json = _json.dumps({
        "delta": {
            "new_ids": [],
            "seen_ids": [],
            "updated_ids": [],
            "failed_urls": [],
        },
        "source_fetch_limit": source_fetch_limit,
    }, ensure_ascii=False)
    if source is not None:
        source.last_checked_at = datetime.utcnow()
        source.last_error_message = error_message
    db.commit()
