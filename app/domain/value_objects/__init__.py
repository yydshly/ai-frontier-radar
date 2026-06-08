"""Domain value objects for candidate pool."""
from app.domain.value_objects.candidate_status import CandidateStatus
from app.domain.value_objects.pagination import Pagination, CandidateFilters

__all__ = ["CandidateStatus", "Pagination", "CandidateFilters"]
