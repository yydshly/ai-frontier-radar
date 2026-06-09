"""Pagination and filter value objects for candidate pool."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Pagination:
    """Immutable pagination parameters."""
    page: int = 1
    page_size: int = 20

    def __post_init__(self):
        """Validate pagination parameters."""
        if self.page < 1:
            object.__setattr__(self, "page", 1)
        if self.page_size < 1:
            object.__setattr__(self, "page_size", 20)
        if self.page_size > 100:
            object.__setattr__(self, "page_size", 100)

    @property
    def offset(self) -> int:
        """Calculate SQL offset."""
        return (self.page - 1) * self.page_size


@dataclass(frozen=True)
class CandidateFilters:
    """Immutable filter parameters for candidate pool queries."""
    source_key: str | None = None
    status: str | None = None
    q: str | None = None


@dataclass
class CandidatePage:
    """Paginated result for candidate pool queries."""
    items: list
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages."""
        if self.total == 0:
            return 0
        return (self.total + self.page_size - 1) // self.page_size

    @property
    def has_next(self) -> bool:
        """Check if there is a next page."""
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        """Check if there is a previous page."""
        return self.page > 1
