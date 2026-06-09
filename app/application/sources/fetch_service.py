"""Source Fetch Service — manual trigger for source probing.

Provides SourceFetchService.run_source() which:
1. Creates a FetchRun in "running" state
2. Calls the appropriate probe (RSS or HTML index) based on fetch_strategy
3. Upserts SourceItems (handled by probe)
4. Updates FetchRun with results and metadata_json.delta
5. Updates Source.last_checked_at / last_success_at / last_error_message
6. Returns SourceFetchResult

Does NOT:
- Run in background (synchronous only)
- Generate InsightCards
- Use Celery/Redis/RQ
"""
import json
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Source, FetchRun
from app.sources.rss_probe import probe_rss_source
from app.sources.html_index_probe import probe_html_index_source


# Supported fetch strategies
SUPPORTED_STRATEGIES = {"rss", "html_index"}


@dataclass
class SourceFetchResult:
    """Result of a manual source fetch operation."""
    fetch_run: FetchRun
    source_key: str
    fetch_strategy: str
    items_found: int
    items_new: int
    items_updated: int
    items_failed: int
    error_message: str | None
    # IDs of items that were new (inserted)
    new_ids: list[int] = field(default_factory=list)
    # IDs of items that were seen (already existed, last_seen_at bumped)
    seen_ids: list[int] = field(default_factory=list)
    # IDs of items that were updated
    updated_ids: list[int] = field(default_factory=list)
    # URLs that failed to process
    failed_urls: list[str] = field(default_factory=list)


class SourceFetchService:
    """Application service for manually fetching a single source."""

    def __init__(self, db: Session):
        self.db = db

    def run_source(self, source_key: str, timeout_seconds: int = 20) -> SourceFetchResult | None:
        """Manually trigger a fetch for the given source_key.

        Args:
            source_key: The source key to fetch.
            timeout_seconds: HTTP request timeout for the probe.

        Returns:
            SourceFetchResult if source found, None if not found.

        Raises:
            No exceptions — all errors are captured in FetchRun.status=failed
            and FetchRun.error_message.
        """
        # Find source
        source = self.db.query(Source).filter(Source.source_key == source_key).first()
        if not source:
            return None

        # Create FetchRun in running state
        fetch_run = FetchRun(
            source_id=source.id,
            source_key=source_key,
            run_type="manual",
            status="running",
            started_at=datetime.utcnow(),
        )
        self.db.add(fetch_run)
        self.db.commit()
        self.db.refresh(fetch_run)

        new_ids: list[int] = []
        seen_ids: list[int] = []
        updated_ids: list[int] = []
        failed_urls: list[str] = []

        try:
            strategy = source.fetch_strategy

            # Check if strategy is supported
            if strategy not in SUPPORTED_STRATEGIES:
                fetch_run.status = "failed"
                fetch_run.error_message = f"unsupported fetch_strategy: {strategy}"
                fetch_run.finished_at = datetime.utcnow()
                source.last_checked_at = datetime.utcnow()
                source.last_error_message = f"unsupported fetch_strategy: {strategy}"
                self.db.commit()
                self.db.refresh(fetch_run)

                return SourceFetchResult(
                    fetch_run=fetch_run,
                    source_key=source_key,
                    fetch_strategy=strategy,
                    items_found=0,
                    items_new=0,
                    items_updated=0,
                    items_failed=0,
                    error_message=fetch_run.error_message,
                    new_ids=[],
                    seen_ids=[],
                    updated_ids=[],
                    failed_urls=[],
                )

            # Call appropriate probe
            if strategy == "rss":
                probe_result = probe_rss_source(self.db, source, timeout_seconds=timeout_seconds)
            elif strategy == "html_index":
                probe_result = probe_html_index_source(self.db, source, timeout_seconds=timeout_seconds)
            else:
                # Should not reach here due to check above
                probe_result = {
                    "items_found": 0,
                    "items_new": 0,
                    "items_updated": 0,
                    "items_failed": 0,
                    "error_message": f"unknown fetch_strategy: {strategy}",
                }

            items_found = probe_result["items_found"]
            items_new = probe_result["items_new"]
            items_updated = probe_result["items_updated"]
            items_failed = probe_result["items_failed"]
            error_message = probe_result["error_message"]

            # Collect IDs of new/seen/updated items from SourceItems just created/updated
            # The probe already committed items. We re-query to get IDs.
            window_start = fetch_run.started_at
            window_end = datetime.utcnow()

            all_items = (
                self.db.query(SourceItem)
                .filter(
                    SourceItem.source_id == source.id,
                    SourceItem.last_seen_at >= window_start,
                    SourceItem.last_seen_at <= window_end,
                )
                .all()
            )

            # Items first_seen_at within window are new; items where last_seen_at > first_seen_at are updated
            # Items where first_seen_at == last_seen_at within window are new
            # But since the probe updates last_seen_at on every hit, we need another approach.
            # The probe increments items_new / items_updated. We distinguish by checking
            # if first_seen_at is very close to last_seen_at (new) or first_seen_at is older (seen/updated).
            for item in all_items:
                delta = (item.last_seen_at - item.first_seen_at).total_seconds()
                if delta < 1.0:
                    new_ids.append(item.id)
                elif item.updated_at > window_start:
                    updated_ids.append(item.id)
                else:
                    seen_ids.append(item.id)

            # failed_urls: we don't have per-item error tracking in probe result
            # so leave empty (could be enhanced later)

            # Update FetchRun
            fetch_run.items_found = items_found
            fetch_run.items_new = items_new
            fetch_run.items_updated = items_updated
            fetch_run.items_failed = items_failed
            fetch_run.finished_at = datetime.utcnow()

            # Determine status and update Source
            if error_message:
                if items_found == 0:
                    fetch_run.status = "failed"
                    source.last_checked_at = datetime.utcnow()
                    source.last_error_message = error_message
                else:
                    fetch_run.status = "partial_failed"
                    source.last_checked_at = datetime.utcnow()
                    source.last_success_at = datetime.utcnow()
                    source.last_error_message = error_message
            elif items_failed > 0 and items_found > items_failed:
                fetch_run.status = "partial_failed"
                fetch_run.error_message = f"{items_failed} item(s) failed"
                source.last_checked_at = datetime.utcnow()
                source.last_success_at = datetime.utcnow()
                source.last_error_message = fetch_run.error_message
            elif items_failed > 0 and items_found == items_failed:
                fetch_run.status = "failed"
                fetch_run.error_message = "All items failed"
                source.last_checked_at = datetime.utcnow()
                source.last_error_message = "All items failed"
            else:
                fetch_run.status = "success"
                source.last_checked_at = datetime.utcnow()
                source.last_success_at = datetime.utcnow()
                source.last_error_message = None

            # Write delta to metadata_json
            fetch_run.metadata_json = json.dumps({
                "delta": {
                    "new_ids": new_ids,
                    "seen_ids": seen_ids,
                    "updated_ids": updated_ids,
                    "failed_urls": failed_urls,
                }
            }, ensure_ascii=False)

            self.db.commit()
            self.db.refresh(fetch_run)

            return SourceFetchResult(
                fetch_run=fetch_run,
                source_key=source_key,
                fetch_strategy=strategy,
                items_found=items_found,
                items_new=items_new,
                items_updated=items_updated,
                items_failed=items_failed,
                error_message=error_message,
                new_ids=new_ids,
                seen_ids=seen_ids,
                updated_ids=updated_ids,
                failed_urls=failed_urls,
            )

        except Exception as e:
            self.db.rollback()

            fetch_run.status = "failed"
            fetch_run.error_message = str(e)
            fetch_run.finished_at = datetime.utcnow()
            source.last_checked_at = datetime.utcnow()
            source.last_error_message = str(e)

            # Write delta with empty results
            fetch_run.metadata_json = json.dumps({
                "delta": {
                    "new_ids": [],
                    "seen_ids": [],
                    "updated_ids": [],
                    "failed_urls": [],
                }
            }, ensure_ascii=False)

            self.db.commit()
            self.db.refresh(fetch_run)

            return SourceFetchResult(
                fetch_run=fetch_run,
                source_key=source_key,
                fetch_strategy=source.fetch_strategy,
                items_found=0,
                items_new=0,
                items_updated=0,
                items_failed=0,
                error_message=str(e),
                new_ids=[],
                seen_ids=[],
                updated_ids=[],
                failed_urls=[],
            )


# Import at bottom to avoid circular import
from app.models import SourceItem
