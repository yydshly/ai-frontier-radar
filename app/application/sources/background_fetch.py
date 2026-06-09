"""Background Source Fetch Service.

Provides background fetch for sources using FastAPI BackgroundTasks.
Encapsulates enqueue logic and background execution with proper DB session isolation.

Does NOT use Celery/Redis/RQ — uses FastAPI BackgroundTasks only.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.db import SessionLocal
from app.models import Source, FetchRun


# Time window for duplicate-running protection (10 minutes)
_RUNNING_WINDOW_MINUTES = 10


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
    ) -> SourceFetchEnqueueResult:
        """Enqueue a source for background fetching.

        Creates a FetchRun(status=running) immediately, then either dispatches a
        background task (if background_tasks provided) or runs synchronously.

        Args:
            source_key: The source key to fetch.
            background_tasks: Optional BackgroundTasks instance from FastAPI.
                             If None, runs synchronously (suitable for scripts/tests).

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
                )
            else:
                # Synchronous execution when no BackgroundTasks available (scripts/tests)
                run_source_fetch_in_background(fetch_run.id)

            return SourceFetchEnqueueResult(
                accepted=True,
                run_id=fetch_run.id,
                status="running",
                message="Fetch enqueued, running in background",
            )

        finally:
            db.close()


def run_source_fetch_in_background(run_id: int) -> None:
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

        strategy = source.fetch_strategy

        # Check if strategy is supported (same logic as SourceFetchService)
        from app.application.sources.fetch_service import SUPPORTED_STRATEGIES
        if strategy not in SUPPORTED_STRATEGIES:
            _finish_run_as_failed(
                db, fetch_run, source,
                error_message=f"unsupported fetch_strategy: {strategy}",
            )
            return

        # Call the appropriate probe
        try:
            if strategy == "rss":
                from app.sources.rss_probe import probe_rss_source
                probe_result = probe_rss_source(db, source, timeout_seconds=20)
            elif strategy == "html_index":
                from app.sources.html_index_probe import probe_html_index_source
                probe_result = probe_html_index_source(db, source, timeout_seconds=20)
            else:
                # Should not reach here due to check above
                probe_result = {
                    "items_found": 0, "items_new": 0, "items_updated": 0,
                    "items_failed": 0,
                    "error_message": f"unknown fetch_strategy: {strategy}",
                }
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

        # Write delta to metadata_json
        fetch_run.metadata_json = _json.dumps({
            "delta": {
                "new_ids": new_ids,
                "seen_ids": seen_ids,
                "updated_ids": updated_ids,
                "failed_urls": [],
            }
        }, ensure_ascii=False)

        db.commit()

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
    db, fetch_run: FetchRun, source: Source | None, error_message: str
) -> None:
    """Mark a FetchRun as failed and update Source timestamps.

    Handles source=None gracefully (source may have been deleted between enqueue and now).
    """
    import json as _json
    fetch_run.status = "failed"
    fetch_run.error_message = error_message
    fetch_run.finished_at = datetime.utcnow()
    fetch_run.metadata_json = _json.dumps({
        "delta": {
            "new_ids": [],
            "seen_ids": [],
            "updated_ids": [],
            "failed_urls": [],
        }
    }, ensure_ascii=False)
    if source is not None:
        source.last_checked_at = datetime.utcnow()
        source.last_error_message = error_message
    db.commit()
