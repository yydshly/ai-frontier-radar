"""Candidate Pool Repository - data access layer for SourceItem-based candidate pool.

This repository provides a clean boundary between the application service
and the database. It operates on SourceItem records but exposes them
through the CandidatePool domain semantics.
"""
from sqlalchemy.orm import Session

from app.models import SourceItem
from app.domain.value_objects.pagination import Pagination, CandidateFilters, CandidatePage


class CandidatePoolRepository:
    """Repository for candidate pool operations on SourceItem records."""

    def __init__(self, db: Session):
        self.db = db

    def list_candidates(
        self,
        filters: CandidateFilters,
        pagination: Pagination,
    ) -> CandidatePage:
        """List candidate items with filters and pagination.

        Args:
            filters: Filter parameters (source_key, status, q)
            pagination: Pagination parameters (page, page_size)

        Returns:
            CandidatePage with items and pagination metadata
        """
        query = self.db.query(SourceItem)

        # Apply filters
        if filters.source_key:
            query = query.filter(SourceItem.source_key == filters.source_key)

        if filters.status:
            query = query.filter(SourceItem.status == filters.status)

        if filters.q:
            pattern = f"%{filters.q}%"
            query = query.filter(
                (SourceItem.title.ilike(pattern)) | (SourceItem.url.ilike(pattern))
            )

        # Get total count before pagination
        total = query.count()

        # Apply ordering and pagination
        items = (
            query
            .order_by(SourceItem.first_seen_at.desc(), SourceItem.id.desc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
            .all()
        )

        return CandidatePage(
            items=items,
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
        )

    def count_candidates(self, filters: CandidateFilters) -> int:
        """Count total candidates matching filters.

        Args:
            filters: Filter parameters

        Returns:
            Total count of matching candidates
        """
        query = self.db.query(SourceItem)

        if filters.source_key:
            query = query.filter(SourceItem.source_key == filters.source_key)

        if filters.status:
            query = query.filter(SourceItem.status == filters.status)

        if filters.q:
            pattern = f"%{filters.q}%"
            query = query.filter(
                (SourceItem.title.ilike(pattern)) | (SourceItem.url.ilike(pattern))
            )

        return query.count()

    def get_by_ids(self, ids: list[int]) -> list[SourceItem]:
        """Get SourceItem records by their IDs.

        Args:
            ids: List of SourceItem IDs

        Returns:
            List of SourceItem records (order not guaranteed)
        """
        if not ids:
            return []
        return self.db.query(SourceItem).filter(SourceItem.id.in_(ids)).all()

    def update_status(self, ids: list[int], status: str) -> int:
        """Update status for multiple SourceItem records.

        Note: This method does NOT commit. The caller (Service layer) is
        responsible for committing the transaction.

        Args:
            ids: List of SourceItem IDs to update
            status: New status value

        Returns:
            Number of records updated
        """
        if not ids:
            return 0

        result = (
            self.db.query(SourceItem)
            .filter(SourceItem.id.in_(ids))
            .update({"status": status}, synchronize_session=False)
        )
        return result

    def mark_ignored(self, ids: list[int]) -> int:
        """Mark items as ignored.

        Args:
            ids: List of SourceItem IDs

        Returns:
            Number of records updated
        """
        return self.update_status(ids, "ignored")

    def mark_compiling(self, ids: list[int]) -> int:
        """Mark items as compiling.

        Args:
            ids: List of SourceItem IDs

        Returns:
            Number of records updated
        """
        return self.update_status(ids, "compiling")
