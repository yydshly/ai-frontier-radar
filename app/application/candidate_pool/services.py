"""Candidate Pool Application Service.

This service contains the business logic for the candidate pool,
orchestrating repository calls and enforcing state transition rules.
"""
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.infrastructure.repositories.candidate_pool_repository import CandidatePoolRepository
from app.domain.value_objects.pagination import Pagination, CandidateFilters, CandidatePage


# Statuses that can be ignored
_IGNORABLE_STATUSES = {"discovered", "failed", "manual_required"}

# Statuses that can be transitioned to compiling
_COMPILABLE_STATUSES = {"discovered", "failed"}

# Statuses that should be skipped during ignore
_SKIP_ON_IGNORE_STATUSES = {"compiled", "ignored", "compiling"}

# Statuses that should be skipped during compile preparation
_SKIP_ON_COMPILE_STATUSES = {"compiled", "ignored", "compiling", "manual_required"}


@dataclass
class CandidateBatchResult:
    """Result of a batch operation on candidates."""
    requested: int = 0
    updated: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)

    def add_error(self, error: str):
        """Add an error message."""
        self.errors.append(error)

    def add_skipped(self, count: int = 1):
        """Add skipped count."""
        self.skipped += count

    def add_updated(self, count: int = 1):
        """Add updated count."""
        self.updated += count


class CandidatePoolService:
    """Application service for candidate pool operations."""

    def __init__(self, db: Session):
        self.repo = CandidatePoolRepository(db)
        self.db = db

    def list_candidates(
        self,
        source_key: str | None = None,
        status: str | None = None,
        q: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> CandidatePage:
        """List candidates with filters and pagination.

        Args:
            source_key: Filter by source key
            status: Filter by status
            q: Search query for title/url
            page: Page number (1-indexed)
            page_size: Items per page (max 100)

        Returns:
            CandidatePage with items and pagination info
        """
        pagination = Pagination(page=page, page_size=page_size)
        filters = CandidateFilters(source_key=source_key, status=status, q=q)
        return self.repo.list_candidates(filters, pagination)

    def ignore_candidates(self, candidate_ids: list[int]) -> CandidateBatchResult:
        """Mark candidates as ignored, respecting state transition rules.

        State transition rules:
        - discovered, failed, manual_required -> ignored (allowed)
        - compiled, ignored, compiling -> skipped (not allowed to ignore)

        Args:
            candidate_ids: List of candidate IDs to ignore

        Returns:
            CandidateBatchResult with counts of updated/skipped/errors
        """
        result = CandidateBatchResult(requested=len(candidate_ids))

        if not candidate_ids:
            return result

        # Fetch all candidates
        candidates = self.repo.get_by_ids(candidate_ids)
        found_ids = {c.id for c in candidates}

        # Identify missing IDs -> skipped
        missing_count = len(candidate_ids) - len(found_ids)
        result.add_skipped(missing_count)

        # Group by current status
        to_ignore_ids = []
        for candidate in candidates:
            if candidate.status in _IGNORABLE_STATUSES:
                to_ignore_ids.append(candidate.id)
            else:
                result.add_skipped(1)

        # Batch update
        if to_ignore_ids:
            updated = self.repo.mark_ignored(to_ignore_ids)
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            result.add_updated(updated)

        return result

    def prepare_compile_candidates(self, candidate_ids: list[int]) -> CandidateBatchResult:
        """Mark candidates as ready for compilation (status = compiling).

        State transition rules:
        - discovered, failed -> compiling (allowed)
        - ignored, compiled, compiling, manual_required -> skipped (not allowed)

        Note: This only marks items as "compiling" - it does NOT trigger
        the actual LLM compilation process to avoid blocking the UI.

        Args:
            candidate_ids: List of candidate IDs to mark for compilation

        Returns:
            CandidateBatchResult with counts of updated/skipped/errors
        """
        result = CandidateBatchResult(requested=len(candidate_ids))

        if not candidate_ids:
            return result

        # Fetch all candidates
        candidates = self.repo.get_by_ids(candidate_ids)
        found_ids = {c.id for c in candidates}

        # Identify missing IDs -> skipped
        missing_count = len(candidate_ids) - len(found_ids)
        result.add_skipped(missing_count)

        # Group by current status
        to_compile_ids = []
        for candidate in candidates:
            if candidate.status in _COMPILABLE_STATUSES:
                to_compile_ids.append(candidate.id)
            else:
                result.add_skipped(1)

        # Batch update
        if to_compile_ids:
            updated = self.repo.mark_compiling(to_compile_ids)
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise
            result.add_updated(updated)

        return result
