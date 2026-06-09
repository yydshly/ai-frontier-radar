"""FetchRun Repository - data access layer for FetchRun records.

Provides query methods for listing and retrieving fetch run records.
Does not contain business logic, does not commit, does not access external network.
"""
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.models import FetchRun


@dataclass
class FetchRunPage:
    """Paginated result for FetchRun list queries."""
    items: list[FetchRun]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1


class FetchRunRepository:
    """Repository for FetchRun data access operations."""

    def __init__(self, db: Session):
        self.db = db

    def list_runs(
        self,
        source_key: str | None = None,
        status: str | None = None,
        page: int = 1,
        page_size: int = 20,
        exclude_test_sources: bool = True,
    ) -> FetchRunPage:
        """List FetchRun records with optional filters and pagination.

        Args:
            source_key: Filter by source key
            status: Filter by run status
            page: Page number (1-indexed)
            page_size: Items per page (max 100)
            exclude_test_sources: If True, exclude test/orphan source keys (default True)

        Returns:
            FetchRunPage with items and pagination metadata
        """
        # Enforce page_size maximum
        page_size = min(page_size, 100)
        page = max(page, 1)

        query = self.db.query(FetchRun)

        if source_key:
            query = query.filter(FetchRun.source_key == source_key)

        if status:
            query = query.filter(FetchRun.status == status)

        if exclude_test_sources:
            from sqlalchemy import not_, or_
            # Build exclusion: "orphan_key", "test_*", "test_sync_enq_*"
            exclusion_conditions = [
                FetchRun.source_key == "orphan_key",
                FetchRun.source_key.like("test_sync_enq_%"),
                FetchRun.source_key.like("test_%"),
            ]
            query = query.filter(not_(or_(*exclusion_conditions)))

        # Get total count before pagination
        total = query.count()

        # Apply ordering (newest first) and pagination
        items = (
            query
            .order_by(FetchRun.started_at.desc().nullslast(), FetchRun.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
            .all()
        )

        return FetchRunPage(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
        )

    def get_by_id(self, run_id: int) -> FetchRun | None:
        """Get a single FetchRun by its ID.

        Args:
            run_id: The FetchRun ID

        Returns:
            FetchRun or None if not found
        """
        return self.db.query(FetchRun).filter(FetchRun.id == run_id).first()

    def get_latest_by_source_keys(self, source_keys: list[str]) -> dict[str, FetchRun]:
        """Get the most recent FetchRun for each given source key.

        Args:
            source_keys: List of source keys to look up

        Returns:
            Dict mapping source_key -> FetchRun (most recent), omitting keys with no runs
        """
        if not source_keys:
            return {}

        # Subquery: for each source_key, find the max started_at
        from sqlalchemy import func

        subq = (
            self.db.query(
                FetchRun.source_key,
                func.max(FetchRun.started_at).label("max_started_at"),
            )
            .filter(FetchRun.source_key.in_(source_keys))
            .group_by(FetchRun.source_key)
            .subquery()
        )

        results = (
            self.db.query(FetchRun)
            .join(subq, (FetchRun.source_key == subq.c.source_key)
                  & (FetchRun.started_at == subq.c.max_started_at))
            .all()
        )

        return {run.source_key: run for run in results}

    def count_by_status(self) -> dict[str, int]:
        """Count FetchRun records grouped by status.

        Returns:
            Dict mapping status -> count
        """
        from sqlalchemy import func

        results = (
            self.db.query(FetchRun.status, func.count(FetchRun.id))
            .group_by(FetchRun.status)
            .all()
        )

        return {status: count for status, count in results}
