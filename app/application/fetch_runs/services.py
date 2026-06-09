"""FetchRun Application Service.

Business logic for fetch run observability:
- Listing runs with filters and pagination
- Fetching run details with estimated related items
- Building source health maps
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.infrastructure.repositories.fetch_run_repository import (
    FetchRunRepository,
    FetchRunPage,
)
from app.models import FetchRun, SourceItem, Source


@dataclass
class SourceHealth:
    """Health summary for a single source based on its latest FetchRun."""
    source_key: str
    latest_status: str | None
    latest_started_at: datetime | None
    latest_finished_at: datetime | None
    latest_items_found: int
    latest_items_new: int
    latest_error_message: str | None


@dataclass
class FetchRunDetail:
    """Detailed view of a single FetchRun with related Source and estimated related items."""
    run: FetchRun
    source: Source | None
    related_items: list[SourceItem]


class FetchRunService:
    """Application service for fetch run observability."""

    # Time window for related items estimation when finished_at is missing
    ESTIMATED_WINDOW_HOURS = 2

    def __init__(self, db: Session):
        self.repo = FetchRunRepository(db)
        self.db = db

    def list_runs(
        self,
        source_key: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> FetchRunPage:
        """List fetch runs with filters and pagination.

        Args:
            source_key: Filter by source key
            status: Filter by run status
            page: Page number (1-indexed)
            page_size: Items per page (max 100)

        Returns:
            FetchRunPage with runs and pagination metadata
        """
        return self.repo.list_runs(
            source_key=source_key,
            status=status,
            page=page,
            page_size=page_size,
        )

    def get_run_detail(self, run_id: int) -> FetchRunDetail | None:
        """Get detailed view of a single FetchRun.

        Args:
            run_id: The FetchRun ID

        Returns:
            FetchRunDetail or None if run not found
        """
        run = self.repo.get_by_id(run_id)
        if not run:
            return None

        # Get the associated Source
        source = self.db.query(Source).filter(Source.id == run.source_id).first()

        # Estimate related SourceItems based on source_key + time window
        related_items = self._estimate_related_items(run)

        return FetchRunDetail(
            run=run,
            source=source,
            related_items=related_items,
        )

    def get_source_health_map(self, source_keys: list[str]) -> dict[str, SourceHealth]:
        """Build health summary for each source key based on latest FetchRun.

        Args:
            source_keys: List of source keys to build health for

        Returns:
            Dict mapping source_key -> SourceHealth
        """
        if not source_keys:
            return {}

        latest_runs = self.repo.get_latest_by_source_keys(source_keys)

        health_map: dict[str, SourceHealth] = {}
        for source_key in source_keys:
            run = latest_runs.get(source_key)
            if run:
                health_map[source_key] = SourceHealth(
                    source_key=source_key,
                    latest_status=run.status,
                    latest_started_at=run.started_at,
                    latest_finished_at=run.finished_at,
                    latest_items_found=run.items_found or 0,
                    latest_items_new=run.items_new or 0,
                    latest_error_message=run.error_message,
                )
            else:
                health_map[source_key] = SourceHealth(
                    source_key=source_key,
                    latest_status=None,
                    latest_started_at=None,
                    latest_finished_at=None,
                    latest_items_found=0,
                    latest_items_new=0,
                    latest_error_message=None,
                )

        return health_map

    def _estimate_related_items(self, run: FetchRun) -> list[SourceItem]:
        """Estimate which SourceItems were found by this FetchRun.

        Uses a time window heuristic since SourceItem doesn't have fetch_run_id.
        If finished_at is available, window is [started_at, finished_at].
        If finished_at is None, window is [started_at, started_at + ESTIMATED_WINDOW_HOURS].

        Args:
            run: The FetchRun to estimate related items for

        Returns:
            List of likely related SourceItems
        """
        if not run.started_at:
            return []

        # Determine window end
        if run.finished_at:
            window_end = run.finished_at
        else:
            window_end = run.started_at + timedelta(hours=self.ESTIMATED_WINDOW_HOURS)

        # Query SourceItems matching source_key within time window
        return (
            self.db.query(SourceItem)
            .filter(
                SourceItem.source_key == run.source_key,
                SourceItem.first_seen_at >= run.started_at,
                SourceItem.first_seen_at <= window_end,
            )
            .order_by(SourceItem.first_seen_at.desc())
            .limit(100)
            .all()
        )
